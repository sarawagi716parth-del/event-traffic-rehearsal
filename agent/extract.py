"""Screen 2 (Describe): turn a pasted event notice into a scenario and a starting plan.

Gemma reads the notice into fixed fields. Every place it names is matched to
the named places list; anything that doesn't match is reported for the officer
to fix on the next screen. Without Gemma, a simple keyword reader does the same
job less well, and the app says so.
"""
from __future__ import annotations

import datetime as dt
import re

from rapidfuzz import fuzz

from sim import places
from sim.models import Closure, CrowdEvent, Diversion, LotLimit, Plan, Scenario

from .brain import BrainError, OllamaBrain
from .schemas import NoticeFields

TIME = re.compile(r"\b(\d{1,2})(?::|\.)?(\d{2})?\s*(am|pm|a\.m\.|p\.m\.)", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"], 1)}


def _times(text):
    out = []
    for h, m, ap in TIME.findall(text):
        h = int(h) % 12 + (12 if ap.lower().startswith("p") else 0)
        out.append(f"{h:02d}:{int(m or 0):02d}")
    return out


def _date(text):
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,})\w*,?\s+(\d{4})", text)
    if m and m.group(2)[:3].lower() in MONTHS:
        return dt.date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1))).isoformat()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    return m.group(0) if m else dt.date.today().isoformat()


def _mentioned(text, kind):
    low = text.lower()
    found = []
    for name, p in places.all_places().items():
        if p["kind"] != kind:
            continue
        keys = [name] + p.get("aliases", [])
        if any(k.lower() in low or fuzz.partial_ratio(k.lower(), low) >= 92 for k in keys if len(k) > 5):
            found.append(name)
    return found


def keyword_fields(text: str) -> NoticeFields:
    times = _times(text)
    crowd = re.search(r"(\d[\d,]{3,})\s*(?:people|fans|visitors|spectators|attendees)", text, re.I)
    venue = (_mentioned(text, "venue") or places.names("venue"))[0]
    return NoticeFields(
        event_name=text.strip().splitlines()[0][:80] if text.strip() else "Event",
        venue=venue, date=_date(text),
        arrival_start=times[1] if len(times) > 1 else "15:00",
        show_start=times[2] if len(times) > 2 else "19:00",
        show_end="22:00",
        closure_start=times[0] if times else None,
        crowd=int(crowd.group(1).replace(",", "")) if crowd else None,
        parking_lots=_mentioned(text, "parking"),
        roads_closed=_mentioned(text, "road"),
        diversion_junctions=[j for j in _mentioned(text, "junction") if "divert" in text.lower()],
        cabs_drop_at_parking="cab" in text.lower() and "drop" in text.lower(),
        shuttles="shuttle" in text.lower(),
    )


def read_notice(text: str, brain) -> tuple[NoticeFields, str, list[str]]:
    """Returns (fields, source, problems)."""
    if isinstance(brain, OllamaBrain):
        venues = ", ".join(places.names("venue"))
        lots = ", ".join(places.names("parking"))
        roads = ", ".join(places.names("road"))
        juncs = ", ".join(places.names("junction"))
        try:
            f, _ = brain.ask(
                "You read police event notices and fill in fixed fields. Use 24-hour HH:MM times and "
                "YYYY-MM-DD dates. Use place names from the lists when they match.",
                f"Known venues: {venues}\nKnown parking lots: {lots}\nKnown roads: {roads}\n"
                f"Known junctions: {juncs}\n\nNotice:\n{text}\n\nFill the JSON fields.", NoticeFields)
            source = "gemma"
        except BrainError:
            f, source = keyword_fields(text), "keywords"
    else:
        f, source = keyword_fields(text), "keywords"
    problems = []
    v = places.match(f.venue, "venue")
    if v is None:
        problems.append(f"Venue '{f.venue}' is not in the places list; picked {places.names('venue')[0]}.")
        v = places.names("venue")[0]
    f.venue = v
    for attr, kind in (("parking_lots", "parking"), ("roads_closed", "road"), ("diversion_junctions", "junction")):
        ok = []
        for n in getattr(f, attr):
            m = places.match(n, kind)
            if m:
                ok.append(m)
            else:
                problems.append(f"'{n}' ({kind}) is not in the places list and was left out.")
        setattr(f, attr, list(dict.fromkeys(ok)))
    return f, source, problems


def to_scenario_and_plan(f: NoticeFields, template: Scenario) -> tuple[Scenario, Plan]:
    """Fill a scenario from the notice, keeping the officer's defaults for everything else."""
    scn = template.model_copy(deep=True)
    ev = scn.events[0] if scn.events else CrowdEvent(name=f.event_name, venue=f.venue, date=f.date)
    ev = ev.model_copy(update={"name": f.event_name, "type": f.event_type, "venue": f.venue, "date": f.date,
                               "arrival_start": f.arrival_start, "show_start": f.show_start,
                               "show_end": f.show_end, **({"crowd": f.crowd} if f.crowd else {})})
    scn.events = [ev]
    scn.title = f"{f.event_name}, {f.date}"
    scn.id = re.sub(r"[^a-z0-9]+", "_", f"{f.event_name}_{f.date}".lower()).strip("_")[:60]
    start = f.closure_start or "16:00"
    plan = Plan(name="Officer's plan (from the notice)",
                closures=[Closure(road=r, start=start, end="23:30", allow=["emergency", "shuttles"])
                          for r in f.roads_closed],
                parking=[LotLimit(lot=l) for l in f.parking_lots],
                dropoffs=list(f.parking_lots) if f.cabs_drop_at_parking else [])
    for j in f.diversion_junctions:
        # Divert away from the venue: block the stretch towards the venue
        plan.diversions.append(Diversion(junction=j, blocked_toward=f.venue, start=start, end="23:30"))
    return scn, plan
