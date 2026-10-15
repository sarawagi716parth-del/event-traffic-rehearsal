"""Builds the traffic for one simulation run: normal trips, event visitors,
cabs, shuttles and ambulance test trips.

The same seed always gives the same normal traffic and ambulance trips, so the
plan run and the normal-evening run can be compared trip by trip.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr

from . import config, network, places
from .models import Plan, Scenario

# Vehicle types. Event visitors' cars and two-wheelers use the class "custom1",
# so a closure can let ticket holders through and keep everyone else out.
VTYPES = {
    "car": dict(vClass="passenger", length=4.5, maxSpeed=19.4, speedDev=0.1),
    "two_wheeler": dict(vClass="motorcycle", length=2.2, maxSpeed=16.7, speedDev=0.1),
    "auto": dict(vClass="passenger", length=3.2, maxSpeed=12.5, speedDev=0.1),
    "visitor_car": dict(vClass="custom1", length=4.5, maxSpeed=19.4, speedDev=0.1),
    "visitor_2w": dict(vClass="custom1", length=2.2, maxSpeed=16.7, speedDev=0.1),
    "cab": dict(vClass="taxi", length=4.3, maxSpeed=16.7, speedDev=0.1),
    "shuttle": dict(vClass="bus", length=10.0, maxSpeed=13.9, speedDev=0.05),
    "ambulance": dict(vClass="emergency", length=6.0, maxSpeed=22.2, speedDev=0.0, speedFactor=1.15),
}

# Who may still pass a closed road (C1.4) -> SUMO vehicle classes
ALLOW_TO_CLASSES = {
    "emergency": ["emergency"],
    "buses": ["bus"],
    "shuttles": ["bus"],
    "ticket_holders": ["custom1"],
    "cabs": ["taxi"],
    "residents": ["custom2"],
}
ALL_ROAD_CLASSES = ["passenger", "motorcycle", "taxi", "custom1", "custom2", "bus", "emergency",
                    "delivery", "truck"]

RAIN_SPEED = {"none": 1.0, "light": 0.85, "heavy": 0.70}  # D2, an assumption
WALK_KMH = 4.0          # C2.9
WALK_DETOUR = 1.3       # walking paths are longer than a straight line
SHUTTLE_KMH = 20.0


@dataclass
class Demand:
    trips: list = field(default_factory=list)          # (depart, id, type, from_edge, to_edge, group)
    visitor_vehicles: int = 0
    lot_loads: dict = field(default_factory=dict)      # lot -> car-equivalents assigned
    lot_capacity: dict = field(default_factory=dict)
    informal_parking: int = 0                          # vehicles that found no space in open lots
    redirected: int = 0                                # vehicles sent on from a full lot
    walk_minutes_avg: float = 0.0
    people_by_lot: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)         # trip id -> group name


def _weighted_edges(index, usable, exclude_xy=None, exclude_r=0.0, net=None):
    out, weights = [], []
    for eid, e in index["edges"].items():
        if eid not in usable:
            continue
        if exclude_xy is not None and net is not None:
            x, y = network.edge_xy_mid(net, eid)
            if math.hypot(x - exclude_xy[0], y - exclude_xy[1]) < exclude_r:
                continue
        out.append(eid)
        weights.append(e["length"] * e["lanes"])
    return out, weights


def _sample_time(rng, start, end, peak_last=7200, peak_share=0.65):
    """Arrival spread (C2.2): busiest in the last two hours before the show."""
    if end - start <= peak_last:
        u = rng.random()
        return start + (end - start) * math.sqrt(u)  # rising towards the show
    if rng.random() < peak_share:
        u = rng.random()
        return end - peak_last + peak_last * math.sqrt(u)
    return rng.uniform(start, end - peak_last)


def _sample_exit(rng, end, exit_minutes):
    """Exit surge (C2.3): most people leave within `exit_minutes` of the end."""
    w = exit_minutes * 60
    if rng.random() < 0.85:
        return end + w * (1 - math.sqrt(1 - rng.random()))  # falling after the end
    return end + rng.uniform(w, 2 * w)


def build_demand(scn: Scenario, plan: Plan | None, seed: int, include_event: bool = True,
                 net_name: str | None = None) -> Demand:
    net = network.load_net(net_name)
    index = network.load_index(net_name)
    usable = set(index["edges"])
    pl = places.all_places(net_name)
    d = Demand()
    begin, end = config.parse_time(scn.sim_begin), config.parse_time(scn.sim_end)

    def add(depart, tid, vtype, frm, to, group):
        if frm == to or depart < begin or depart >= end:
            return
        d.trips.append((round(depart, 1), tid, vtype, frm, to, group))
        d.groups[tid] = group

    def mid(eid):
        return network.edge_xy_mid(net, eid)

    # ---------- B: normal traffic (same for the plan run and the normal evening) ----------
    rng = random.Random(seed)
    interior, w_int = _weighted_edges(index, usable)
    origin_places = {n: p for n, p in pl.items() if p["kind"] == "origin"}
    entry_edges = [e for n, p in origin_places.items() if not p.get("interior") for e in p.get("edges", [])]
    curve = scn.normal.hourly_curve
    total_curve = sum(curve)
    mix = scn.normal.vehicle_mix
    mix_types = {"car": "car", "two_wheeler": "two_wheeler", "auto": "auto"}
    types, type_w = zip(*[(mix_types[k], v) for k, v in mix.items() if k in mix_types])
    n_id = 0
    for t0 in range(begin, end, 3600):
        hour = (t0 // 3600) % 24
        count = int(round(scn.normal.total_daily_trips * curve[hour] / total_curve))
        for _ in range(count):
            dep = rng.uniform(t0, t0 + 3600)
            vt = rng.choices(types, type_w)[0]
            if entry_edges and rng.random() < scn.normal.outside_share:
                if rng.random() < 0.5:
                    frm, to = rng.choice(entry_edges), rng.choices(interior, w_int)[0]
                else:
                    frm, to = rng.choices(interior, w_int)[0], rng.choice(entry_edges)
            else:
                for _try in range(10):
                    frm, to = rng.choices(interior, w_int, k=2)
                    a, b = mid(frm), mid(to)
                    if math.hypot(a[0] - b[0], a[1] - b[1]) > 1500:
                        break
            add(dep, f"bg{n_id}", vt, frm, to, "normal")
            n_id += 1

    # ---------- E2: ambulance test trips (also in the normal evening) ----------
    hospitals = [pl[h] for h in scn.protected_hospitals if h in pl]
    for ev in scn.events:
        venue = pl.get(ev.venue)
        if not venue or not hospitals:
            continue
        starts = list(venue.get("edges", []))[:1]
        near = sorted((p for p in pl.values() if p["kind"] == "junction" and "node" in p),
                      key=lambda p: p["dist_from_venue_km"].get(ev.venue, 99))[:2]
        for j in near:
            outs = [e.getID() for e in net.getNode(j["node"]).getOutgoing() if e.getID() in usable]
            if outs:
                starts.append(outs[0])
        a0 = config.parse_time(ev.arrival_start)
        a1 = config.parse_time(ev.show_end) + 3600
        k = 0
        for t in range(a0, a1, scn.ambulance_every_min * 60):
            for h in hospitals:
                for s in starts:
                    add(t, f"amb_{h['name'][:12].replace(' ', '')}_{k}", "ambulance", s, h["edges"][0],
                        f"ambulance|{h['name']}")
                    k += 1

    if not include_event or plan is None:
        d.trips.sort()
        return d

    # ---------- C2: event visitors ----------
    rng = random.Random(seed * 7919 + 1)
    open_lots = [l for l in plan.open_lots() if l in pl and pl[l]["kind"] == "parking"]
    limits = {}
    for lot in plan.parking:
        if lot.lot in pl:
            limits[lot.lot] = lot.limit or pl[lot.lot].get("capacity", 500)
    d.lot_capacity = dict(limits)
    loads = {l: 0.0 for l in open_lots}
    people_by_lot = {l: 0.0 for l in open_lots}
    walk_people_min = 0.0
    walk_people = 0.0
    shuttle_lots = {s.lot for s in plan.shuttles}

    def walk_min_from(xy, venue_xy, lot_name=None):
        dist_km = math.hypot(xy[0] - venue_xy[0], xy[1] - venue_xy[1]) / 1000
        if lot_name in shuttle_lots:
            sh = next(s for s in plan.shuttles if s.lot == lot_name)
            return dist_km * 1.4 / SHUTTLE_KMH * 60 + sh.every_minutes / 2 + 3
        return dist_km * WALK_DETOUR / WALK_KMH * 60

    for ei, ev in enumerate(scn.events):
        venue = pl.get(ev.venue)
        if not venue:
            continue
        vxy = venue["xy"]
        informal_edges, _ = _weighted_edges(index, usable, net=None)
        informal_edges = [e for e in informal_edges
                          if 250 < math.hypot(mid(e)[0] - vxy[0], mid(e)[1] - vxy[1]) < 900]
        interior_far, w_far = _weighted_edges(index, usable, exclude_xy=vxy, exclude_r=1200, net=net)
        counts = ev.vehicles()
        shares = ev.origin_shares
        total_share = sum(shares.values()) or 1
        a0, s0, e0 = (config.parse_time(ev.arrival_start), config.parse_time(ev.show_start),
                      config.parse_time(ev.show_end))
        ppv = ev.people_per_vehicle

        def pick_origin():
            names_ = list(shares)
            name_ = rng.choices(names_, [shares[n] / total_share for n in names_])[0]
            o = pl.get(name_)
            if o is None or o.get("interior") or not o.get("edges"):
                e = rng.choices(interior_far, w_far)[0]
                return name_, e
            return name_, rng.choice(o["edges"])

        def choose_lot(origin_name, from_xy):
            for a in plan.assignments:
                if a.origin == origin_name and a.lot in loads and rng.random() < a.share:
                    return a.lot
            if not open_lots:
                return None
            return min(open_lots, key=lambda l: math.hypot(pl[l]["xy"][0] - from_xy[0],
                                                           pl[l]["xy"][1] - from_xy[1]))

        # Private vehicles, in departure order so lots fill first-come first-served
        private = []
        for mode, vtype, units in (("car", "visitor_car", 1.0), ("two_wheeler", "visitor_2w", 0.25)):
            for i in range(counts.get(mode, 0)):
                origin_name, frm = pick_origin()
                private.append((_sample_time(rng, a0, s0), mode, vtype, units, origin_name, frm))
        private.sort()
        for i, (dep, mode, vtype, units, origin_name, frm) in enumerate(private):
            fxy = mid(frm)
            lot = choose_lot(origin_name, fxy)
            if lot is not None and loads[lot] + units > limits[lot]:
                d.redirected += 1
                spare = [l for l in open_lots if loads[l] + units <= limits[l]]
                lot = min(spare, key=lambda l: math.hypot(pl[l]["xy"][0] - pl[lot]["xy"][0],
                                                          pl[l]["xy"][1] - pl[lot]["xy"][1])) if spare else None
            if lot is None:
                d.informal_parking += 1
                dest = rng.choice(informal_edges) if informal_edges else venue["edges"][0]
                walk = walk_min_from(mid(dest), vxy)
            else:
                loads[lot] += units
                people_by_lot[lot] += ppv.get(mode, 1)
                dest = rng.choice(pl[lot]["edges"])
                walk = walk_min_from(pl[lot]["xy"], vxy, lot)
            walk_people_min += walk * ppv.get(mode, 1)
            walk_people += ppv.get(mode, 1)
            tid = f"ev{ei}_{mode[:3]}{i}"
            add(dep, tid, vtype, frm, dest, f"visitor|{lot or 'informal'}")
            add(_sample_exit(rng, e0, ev.exit_minutes), tid + "_out", vtype, dest, frm, "visitor_exit")
            d.visitor_vehicles += 1

        # Cabs and autos (C2.8): drop at the drop-off point, then leave
        drops = [x for x in plan.dropoffs if x in pl]
        for i in range(counts.get("cab", 0)):
            origin_name, frm = pick_origin()
            fxy = mid(frm)
            if drops:
                dp = min(drops, key=lambda x: math.hypot(pl[x]["xy"][0] - fxy[0], pl[x]["xy"][1] - fxy[1]))
                dpe = (pl[dp].get("edges") or [None])[0]
                if dpe is None:  # a junction used as drop-off point
                    outs = [e.getID() for e in net.getNode(pl[dp]["node"]).getIncoming()
                            if e.getID() in usable]
                    dpe = outs[0] if outs else venue["edges"][0]
                dxy = pl[dp]["xy"]
                walk = walk_min_from(dxy, vxy, dp if pl[dp]["kind"] == "parking" else None)
            else:
                dpe, dxy, walk = venue["edges"][0], vxy, 3.0
            walk_people_min += walk * ppv.get("cab", 1)
            walk_people += ppv.get("cab", 1)
            dep = _sample_time(rng, a0, s0)
            travel = math.hypot(fxy[0] - dxy[0], fxy[1] - dxy[1]) / 6.0
            tid = f"ev{ei}_cab{i}"
            add(dep, tid, "cab", frm, dpe, "visitor|cab")
            add(dep + travel + 120, tid + "_empty", "cab", dpe, rng.choices(interior, w_int)[0], "cab_empty")
            ex = _sample_exit(rng, e0, ev.exit_minutes)
            add(ex - 1800 * rng.random() - 300, tid + "_pickup", "cab", rng.choices(interior, w_int)[0], dpe,
                "cab_empty")
            add(ex, tid + "_out", "cab", dpe, frm, "visitor_exit")
            d.visitor_vehicles += 1

        # Shuttles (F5): buses between each lot and the venue
        for s in plan.shuttles:
            if s.lot not in pl:
                continue
            t, j = config.parse_time(s.start), 0
            stop = config.parse_time(s.end)
            while t < stop:
                add(t, f"sh_{ei}_{j}_go", "shuttle", pl[s.lot]["edges"][0], venue["edges"][0], "shuttle")
                add(t + 60, f"sh_{ei}_{j}_back", "shuttle", venue["edges"][0], pl[s.lot]["edges"][0], "shuttle")
                t += s.every_minutes * 60
                j += 1

    d.lot_loads = {k: round(v) for k, v in loads.items()}
    d.people_by_lot = {k: round(v) for k, v in people_by_lot.items()}
    d.walk_minutes_avg = round(walk_people_min / walk_people, 1) if walk_people else 0.0
    d.trips.sort()
    return d


def write_routes(d: Demand, path, rain: str = "none"):
    f = RAIN_SPEED.get(rain, 1.0)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<routes>"]
    for name, attrs in VTYPES.items():
        a = dict(attrs)
        a["speedFactor"] = round(a.get("speedFactor", 1.0) * f, 3)
        attr = " ".join(f'{k}="{v}"' for k, v in a.items())
        lines.append(f'  <vType id="{name}" {attr}/>')
    for dep, tid, vt, frm, to, _g in d.trips:
        lines.append(f'  <trip id={quoteattr(tid)} type="{vt}" depart="{dep}" from="{frm}" to="{to}" '
                     f'departLane="best" departSpeed="max"/>')
    lines.append("</routes>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
