"""Data formats for scenarios and plans, checked with Pydantic.

A *scenario* is the facts of the day (the event, the crowd, normal traffic).
A *plan* is what the police or the agent decides (closures, diversions, parking).
Field names follow docs/01-simulation-inputs.md.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ALLOW_CHOICES = ("emergency", "buses", "shuttles", "ticket_holders", "cabs", "residents")

# A standard two-peak curve: share of the day's normal trips starting in each hour.
DEFAULT_HOURLY = [0.5, 0.3, 0.2, 0.2, 0.4, 1.0, 2.5, 5.0, 7.5, 7.0, 6.0, 5.5,
                  5.5, 5.5, 5.5, 5.5, 6.5, 7.5, 8.0, 7.0, 5.0, 3.0, 1.8, 1.0]


class NormalTraffic(BaseModel):
    total_daily_trips: int = Field(60000, ge=0, description="B3, tuned by hand")
    hourly_curve: list[float] = Field(default_factory=lambda: list(DEFAULT_HOURLY))
    vehicle_mix: dict[str, float] = Field(
        default_factory=lambda: {"car": 0.55, "two_wheeler": 0.35, "auto": 0.10})
    outside_share: float = Field(0.15, ge=0, le=1, description="B6, trips from outside the city")

    @field_validator("hourly_curve")
    @classmethod
    def _24(cls, v):
        if len(v) != 24:
            raise ValueError("hourly_curve needs 24 values")
        return v


class CrowdEvent(BaseModel):
    type: Literal["concert", "match", "festival_market"] = "concert"
    name: str
    venue: str
    date: str
    arrival_start: str = "15:00"
    show_start: str = "19:00"
    show_end: str = "22:00"
    crowd: int = Field(20000, ge=0)
    exit_minutes: int = Field(45, ge=5, le=240, description="C2.3, most people leave within this")
    mode_split: dict[str, float] = Field(
        default_factory=lambda: {"car": 0.50, "two_wheeler": 0.25, "cab": 0.20, "walk": 0.05})
    people_per_vehicle: dict[str, float] = Field(
        default_factory=lambda: {"car": 2.5, "two_wheeler": 1.5, "cab": 2.5})
    origin_shares: dict[str, float] = Field(default_factory=lambda: {
        "Chandigarh": 0.50, "Mohali": 0.20, "Panchkula and Zirakpur": 0.15, "Outside the Tricity": 0.15})
    notes: str = ""

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        dt.date.fromisoformat(v)
        return v

    def vehicles(self) -> dict[str, int]:
        """C2.4 and C2.5: people to vehicles."""
        out = {}
        for mode in ("car", "two_wheeler", "cab"):
            share = self.mode_split.get(mode, 0)
            ppv = max(self.people_per_vehicle.get(mode, 1.0), 1.0)
            out[mode] = int(round(self.crowd * share / ppv))
        return out


class Scenario(BaseModel):
    id: str
    title: str
    events: list[CrowdEvent]
    normal: NormalTraffic = Field(default_factory=NormalTraffic)
    protected_hospitals: list[str] = Field(default_factory=list)
    ambulance_limit_min: float = 5.0
    ambulance_every_min: int = 15
    rain: Literal["none", "light", "heavy"] = "none"
    sim_begin: str = "13:00"
    sim_end: str = "25:00"
    assumptions: list[str] = Field(default_factory=list)

    def day_type(self) -> str:
        """B1: weekday, Saturday, Sunday or public holiday."""
        d = dt.date.fromisoformat(self.events[0].date)
        try:
            import holidays

            if d in holidays.India(years=d.year):
                return "public holiday"
        except Exception:
            pass
        return {5: "Saturday", 6: "Sunday"}.get(d.weekday(), "weekday")


class Closure(BaseModel):
    road: str
    start: str
    end: str
    allow: list[str] = Field(default_factory=lambda: ["emergency"])
    direction: Literal["both", "forward", "back"] = "both"


class Diversion(BaseModel):
    junction: str
    blocked_toward: str
    send_to: str = ""
    start: str
    end: str
    allow: list[str] = Field(default_factory=lambda: ["emergency", "shuttles"])


class LotLimit(BaseModel):
    lot: str
    limit: int | None = None  # None means use the lot's own capacity


class Assignment(BaseModel):
    origin: str
    lot: str
    share: float = Field(1.0, gt=0, le=1)


class Shuttle(BaseModel):
    lot: str
    buses: int = Field(10, ge=1, le=60)
    every_minutes: int = Field(5, ge=1, le=60)
    start: str = "15:00"
    end: str = "23:30"


class Plan(BaseModel):
    name: str = "Draft plan"
    description: str = ""
    closures: list[Closure] = Field(default_factory=list)
    diversions: list[Diversion] = Field(default_factory=list)
    parking: list[LotLimit] = Field(default_factory=list)
    assignments: list[Assignment] = Field(default_factory=list)
    dropoffs: list[str] = Field(default_factory=list)
    shuttles: list[Shuttle] = Field(default_factory=list)

    def open_lots(self) -> list[str]:
        return [p.lot for p in self.parking]

    def plain_lines(self) -> list[str]:
        """The plan in plain words, for officers and the advisory."""
        out = []
        for c in self.closures:
            out.append(f"Close {c.road} from {c.start} to {c.end} (open to: {', '.join(c.allow) or 'nobody'})")
        for d in self.diversions:
            out.append(f"At {d.junction}, stop traffic towards {d.blocked_toward} from {d.start} to {d.end}"
                       + (f"; send it towards {d.send_to}" if d.send_to else ""))
        for p in self.parking:
            out.append(f"Open parking at {p.lot}" + (f" (limit {p.limit} cars)" if p.limit else ""))
        for a in self.assignments:
            out.append(f"Send {int(a.share * 100)}% of visitors from {a.origin} to {a.lot}")
        if self.dropoffs:
            out.append("Cabs and autos drop people at: " + ", ".join(self.dropoffs))
        for s in self.shuttles:
            out.append(f"Shuttle from {s.lot}: {s.buses} buses, one every {s.every_minutes} min, {s.start} to {s.end}")
        return out
