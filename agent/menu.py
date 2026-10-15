"""The menu: the only actions the agent may take, each checked before it runs.

Every place name is matched against the named places list (guardrail 2). A
small spelling slip is corrected; anything else is rejected with a message
that goes back to Gemma.
"""
from __future__ import annotations

from sim import config, places
from sim.models import (ALLOW_CHOICES, Assignment, Closure, Diversion, LotLimit, Plan,
                        Scenario, Shuttle)

from .schemas import Change

MENU_TEXT = """\
close_road(road, start, end, allow)  close a named ROAD; allow = list from [emergency, buses, shuttles, ticket_holders, cabs]
open_road(road)                      remove a closure from the plan
set_diversion(junction, blocked_toward, send_to, start, end)  at a JUNCTION, stop traffic heading to blocked_toward
remove_diversion(junction)           remove a diversion from the plan
open_parking(lot, limit)             open a PARKING lot; limit = max cars (optional)
close_parking(lot)                   close a PARKING lot
assign_arrivals(origin, lot, share)  send a share (0-1) of visitors from an ORIGIN to a PARKING lot
set_dropoff(point)                   where cabs and autos drop people (a PARKING lot or JUNCTION); replaces the list
add_shuttle(lot, buses, every_minutes, start, end)  shuttle buses between a PARKING lot and the venue
Times are HH:MM in 24-hour form, for example 16:00 or 23:30."""


class MenuError(ValueError):
    pass


def _place(text, kind, label):
    name = places.match(text, kind)
    if name is None:
        kinds = kind if isinstance(kind, tuple) else (kind,)
        options = [n for k in kinds for n in places.names(k)]
        raise MenuError(f"'{text}' is not a known {label}. Choose one of: {', '.join(options[:25])}")
    return name


def _time(value, label):
    try:
        t = config.parse_time(value)
    except Exception as exc:
        raise MenuError(f"{label} '{value}' is not a time like 16:00") from exc
    if not 0 <= t <= 30 * 3600:
        raise MenuError(f"{label} '{value}' is out of range")
    return config.hhmm(t)


def _allow(values):
    if values is None:
        return ["emergency"]
    if isinstance(values, str):
        values = [v.strip() for v in values.replace(";", ",").split(",") if v.strip()]
    out = []
    for v in values:
        key = str(v).lower().replace(" ", "_").replace("-", "_")
        key = {"emergency_vehicles": "emergency", "ambulances": "emergency", "bus": "buses",
               "shuttle": "shuttles", "ticket_holder": "ticket_holders", "visitors": "ticket_holders",
               "cab": "cabs", "taxis": "cabs", "autos": "cabs"}.get(key, key)
        if key not in ALLOW_CHOICES:
            raise MenuError(f"allow value '{v}' must be one of {list(ALLOW_CHOICES)}")
        out.append(key)
    if "emergency" not in out:
        out.insert(0, "emergency")  # emergency access is never traded away
    return sorted(set(out), key=out.index)


def apply_change(plan: Plan, ch: Change, scn: Scenario) -> tuple[Plan, str]:
    """Returns the changed plan and a one-line description. Raises MenuError."""
    p = plan.model_copy(deep=True)
    a = ch.args or {}
    act = ch.action
    if act == "close_road":
        road = _place(a.get("road"), "road", "ROAD")
        start = _time(a.get("start", "16:00"), "start")
        end = _time(a.get("end", "23:30"), "end")
        p.closures = [c for c in p.closures if c.road != road]
        p.closures.append(Closure(road=road, start=start, end=end, allow=_allow(a.get("allow"))))
        return p, f"Close {road} {start}-{end}"
    if act == "open_road":
        road = _place(a.get("road"), "road", "ROAD")
        if not any(c.road == road for c in p.closures):
            raise MenuError(f"{road} is not closed in the current plan")
        p.closures = [c for c in p.closures if c.road != road]
        return p, f"Reopen {road}"
    if act == "set_diversion":
        j = _place(a.get("junction"), ("junction",), "JUNCTION")
        toward = _place(a.get("blocked_toward"), ("junction", "parking", "venue"), "place")
        send = _place(a.get("send_to"), ("junction",), "JUNCTION") if a.get("send_to") else ""
        if toward == j:
            raise MenuError("blocked_toward must be a different place from the junction")
        start = _time(a.get("start", "16:00"), "start")
        end = _time(a.get("end", "23:30"), "end")
        p.diversions = [d for d in p.diversions if d.junction != j]
        p.diversions.append(Diversion(junction=j, blocked_toward=toward, send_to=send, start=start, end=end,
                                      allow=_allow(a.get("allow", ["emergency", "shuttles"]))))
        return p, f"Diversion at {j} (no traffic towards {toward}) {start}-{end}"
    if act == "remove_diversion":
        j = _place(a.get("junction"), "junction", "JUNCTION")
        if not any(d.junction == j for d in p.diversions):
            raise MenuError(f"There is no diversion at {j} in the current plan")
        p.diversions = [d for d in p.diversions if d.junction != j]
        return p, f"Remove diversion at {j}"
    if act == "open_parking":
        lot = _place(a.get("lot"), "parking", "PARKING lot")
        limit = a.get("limit")
        cap = places.all_places()[lot].get("capacity")
        if limit is not None:
            limit = int(limit)
            if limit <= 0:
                raise MenuError("limit must be positive")
            if cap and limit > cap:
                raise MenuError(f"{lot} holds about {cap} cars; the limit cannot be higher")
        p.parking = [x for x in p.parking if x.lot != lot] + [LotLimit(lot=lot, limit=limit)]
        return p, f"Open {lot}" + (f" (limit {limit})" if limit else "")
    if act == "close_parking":
        lot = _place(a.get("lot"), "parking", "PARKING lot")
        if not any(x.lot == lot for x in p.parking):
            raise MenuError(f"{lot} is not open in the current plan")
        p.parking = [x for x in p.parking if x.lot != lot]
        p.assignments = [x for x in p.assignments if x.lot != lot]
        p.dropoffs = [x for x in p.dropoffs if x != lot]
        p.shuttles = [x for x in p.shuttles if x.lot != lot]
        if not p.parking:
            raise MenuError("At least one parking lot must stay open")
        return p, f"Close {lot}"
    if act == "assign_arrivals":
        origin = _place(a.get("origin"), "origin", "ORIGIN")
        lot = _place(a.get("lot"), "parking", "PARKING lot")
        if not any(x.lot == lot for x in p.parking):
            raise MenuError(f"{lot} is not open; use open_parking first")
        share = float(a.get("share", 1.0))
        if not 0 < share <= 1:
            raise MenuError("share must be between 0 and 1")
        p.assignments = [x for x in p.assignments if not (x.origin == origin and x.lot == lot)]
        p.assignments.append(Assignment(origin=origin, lot=lot, share=share))
        return p, f"Send {int(share * 100)}% of visitors from {origin} to {lot}"
    if act == "set_dropoff":
        pts = a.get("point") or a.get("points")
        pts = pts if isinstance(pts, list) else [pts]
        names = [_place(x, ("parking", "junction"), "PARKING lot or JUNCTION") for x in pts]
        p.dropoffs = names
        return p, "Cabs drop at " + ", ".join(names)
    if act == "add_shuttle":
        lot = _place(a.get("lot"), "parking", "PARKING lot")
        if not any(x.lot == lot for x in p.parking):
            raise MenuError(f"{lot} is not open; use open_parking first")
        sh = Shuttle(lot=lot, buses=int(a.get("buses", 10)), every_minutes=int(a.get("every_minutes", 5)),
                     start=_time(a.get("start", scn.events[0].arrival_start), "start"),
                     end=_time(a.get("end", "23:30"), "end"))
        p.shuttles = [x for x in p.shuttles if x.lot != lot] + [sh]
        return p, f"Shuttle from {lot} every {sh.every_minutes} min"
    raise MenuError(f"Unknown action {act}")


def check_plan(plan: Plan) -> tuple[Plan, list[str]]:
    """Drop any part of a plan that uses a place missing from the map, and say what was dropped.

    Used when loading a saved plan (for example the December 2024 police plan) on a map
    where a few named places could not be found yet.
    """
    p = plan.model_copy(deep=True)
    warn = []

    def ok(name, kind):
        m = places.match(name, kind)
        if m is None:
            warn.append(f"Left out '{name}': not on the map yet (add it in data/places_manual.json)")
        return m

    p.closures = [c.model_copy(update={"road": ok(c.road, "road")}) for c in p.closures if ok(c.road, "road")]
    keep = []
    for d in p.diversions:
        j, t = ok(d.junction, "junction"), ok(d.blocked_toward, ("junction", "parking", "venue"))
        if j and t:
            s = places.match(d.send_to, "junction") if d.send_to else ""
            keep.append(d.model_copy(update={"junction": j, "blocked_toward": t, "send_to": s or ""}))
    p.diversions = keep
    p.parking = [x.model_copy(update={"lot": ok(x.lot, "parking")}) for x in p.parking if ok(x.lot, "parking")]
    p.assignments = [a for a in p.assignments if ok(a.origin, "origin") and ok(a.lot, "parking")]
    p.dropoffs = [ok(x, ("parking", "junction")) for x in p.dropoffs if ok(x, ("parking", "junction"))]
    p.shuttles = [s.model_copy(update={"lot": ok(s.lot, "parking")}) for s in p.shuttles if ok(s.lot, "parking")]
    return p, sorted(set(warn))


def fill_scenario_defaults(scn: Scenario) -> tuple[Scenario, list[str]]:
    """E1: if no protected hospitals are listed, use the ones the map build found near the venue."""
    s = scn.model_copy(deep=True)
    notes = []
    all_p = places.all_places()
    known = [h for h in s.protected_hospitals if h in all_p]
    if len(known) < len(s.protected_hospitals):
        notes.append("Some listed hospitals are not on the map and were left out.")
    if not known:
        venues = {e.venue for e in s.events}
        known = [n for n, p in all_p.items() if p["kind"] == "hospital" and (p.get("near") in venues or
                 min(p.get("dist_from_venue_km", {}).get(v, 99) for v in venues) <= 3)]
        if known:
            notes.append(f"Protected hospitals taken from the map near the venue: {', '.join(known)}. Please confirm.")
    s.protected_hospitals = known
    for ev in s.events:
        v = places.match(ev.venue, "venue")
        if v:
            ev.venue = v
        else:
            notes.append(f"Venue '{ev.venue}' is not on the map.")
    for ev in s.events:
        fixed = {}
        for k, share in ev.origin_shares.items():
            m = places.match(k, "origin")
            if m:
                fixed[m] = fixed.get(m, 0) + share
            else:
                notes.append(f"Visitor origin '{k}' is not on the map; its share was left out.")
        ev.origin_shares = fixed
    return s, notes
