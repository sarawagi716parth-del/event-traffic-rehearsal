"""The fixed answer formats Gemma must reply in (guardrail 1)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PLAN_ACTIONS = (
    "close_road", "open_road", "set_diversion", "remove_diversion",
    "open_parking", "close_parking", "assign_arrivals", "set_dropoff", "add_shuttle",
)


class Change(BaseModel):
    action: Literal[PLAN_ACTIONS]  # type: ignore[valid-type]
    args: dict = Field(default_factory=dict)
    reason: str = Field("", max_length=400)


class RoundReply(BaseModel):
    diagnosis: str = Field(..., max_length=800)
    changes: list[Change] = Field(default_factory=list, max_length=3)  # guardrail 3: small steps
    expected_effect: str = Field("", max_length=500)
    stop: bool = False


class NoticeFields(BaseModel):
    """What Gemma reads from a pasted event notice (screen 2, Describe)."""
    event_name: str
    event_type: Literal["concert", "match", "festival_market"] = "concert"
    venue: str
    date: str = Field(..., description="YYYY-MM-DD")
    arrival_start: str = Field("15:00", description="HH:MM, 24-hour")
    show_start: str = Field("19:00", description="HH:MM, 24-hour")
    show_end: str = Field("22:00", description="HH:MM, 24-hour")
    crowd: int | None = None
    parking_lots: list[str] = Field(default_factory=list)
    roads_closed: list[str] = Field(default_factory=list)
    closure_start: str | None = None
    diversion_junctions: list[str] = Field(default_factory=list)
    roads_to_avoid: list[str] = Field(default_factory=list)
    cabs_drop_at_parking: bool = False
    shuttles: bool = False


class TextDraft(BaseModel):
    text: str


class AdvisoryDraft(BaseModel):
    english: str
    hindi: str
    punjabi: str
