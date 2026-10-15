"""Turns raw run output into the numbers the agent and the officer see.

Every number compares the plan run with the normal evening run of the same
seed (same normal traffic, same ambulance trips). See the metric table in
docs/03-agent-design.md.
"""
from __future__ import annotations

import math
import statistics as st
from collections import defaultdict

from . import config, network, places
from .models import Plan, Scenario


def _edge_series(raw):
    """edge -> {interval_begin: (traveltime, entered, speed)}"""
    return {e: {b: (tt, n, sp) for b, tt, n, sp in rows} for e, rows in raw["edges"].items()}


def _sensitive_closure_hours(plan: Plan, pl: dict) -> float:
    hours = 0.0
    for c in plan.closures:
        p = pl.get(c.road)
        if p and p.get("sensitive_area"):
            hours += max(0, config.parse_time(c.end) - config.parse_time(c.start)) / 3600
    for d in plan.diversions:
        p = pl.get(d.junction)
        if p and p.get("sensitive_area"):
            hours += max(0, config.parse_time(d.end) - config.parse_time(d.start)) / 3600
    return round(hours, 1)


def seed_metrics(scn: Scenario, plan: Plan, raw: dict, normal: dict, net_name=None) -> dict:
    index = network.load_index(net_name)
    net = network.load_net(net_name)
    pl = places.all_places(net_name)
    eidx = index["edges"]
    groups = raw["groups"]
    pt, nt = raw["trips"], normal["trips"]

    # ---- delay ----
    total_plan = sum(v[0] for v in pt.values())
    total_norm = sum(v[0] for v in nt.values())
    extra_vh = (total_plan - total_norm) / 3600

    visitor = [v[0] for k, v in pt.items() if groups.get(k, "").startswith("visitor")]
    others = [pt[k][0] - nt[k][0] for k in pt if groups.get(k) == "normal" and k in nt]

    # ---- ambulances (E2, E3) ----
    amb = defaultdict(list)
    for k, v in pt.items():
        g = groups.get(k, "")
        if g.startswith("ambulance|") and k in nt:
            hosp = g.split("|", 1)[1]
            ok_plan, ok_norm = v[2], nt[k][2]
            amb[hosp].append((v[1] / 60, nt[k][1] / 60, ok_plan and ok_norm))
    amb_out = {}
    for hosp, rows in amb.items():
        extra = [p - n for p, n, ok in rows if ok]
        unfinished = sum(1 for *_, ok in rows if not ok)
        amb_out[hosp] = {
            "normal_min": round(st.mean(n for _, n, _ in rows), 1),
            "plan_min": round(st.mean(p for p, _, _ in rows), 1),
            "worst_extra_min": round(max(extra) if extra else 99.0, 1),
            "unfinished": unfinished,
        }

    # ---- gridlock (G4) ----
    inserted = float(raw["stats"].get("vehicles", {}).get("inserted", len(pt)) or 1)
    jumps = float(raw["stats"].get("teleports", {}).get("total", 0))

    # ---- roads: extra wait per road and per named junction ----
    ps, ns = _edge_series(raw), _edge_series(normal)
    road_extra = {}  # edge -> worst extra minutes per vehicle in any 5-min interval
    edge_extra_vh = defaultdict(float)
    interval_extra = defaultdict(lambda: defaultdict(float))  # edge -> begin -> extra veh-s
    for eid, rows in ps.items():
        if eid not in eidx:
            continue
        ff = eidx[eid]["length"] / max(eidx[eid]["speed"], 1)
        worst = 0.0
        for b, (tt, n, sp) in rows.items():
            ntt = ns.get(eid, {}).get(b, (ff, 0, 0))[0]
            nn = ns.get(eid, {}).get(b, (ff, 0, 0))[1]
            extra_veh_s = n * (tt - ff) - nn * (ntt - ff)
            interval_extra[eid][b] = extra_veh_s
            edge_extra_vh[eid] += extra_veh_s / 3600
            if n >= 3:
                worst = max(worst, (tt - ntt) / 60)
        if worst > 0.25:
            road_extra[eid] = round(worst, 1)

    junctions = []
    for name, p in pl.items():
        if p["kind"] not in ("junction", "venue") or not p.get("approach_edges"):
            continue
        appr = [e for e in p["approach_edges"] if e in eidx]
        per_b = defaultdict(float)
        for e in appr:
            for b, v in interval_extra.get(e, {}).items():
                per_b[b] += v
        total = sum(per_b.values()) / 3600
        jam_len, longest_wait = 0.0, 0.0
        times = sorted({b for e in appr for b in ps.get(e, {})})
        for b in times:
            jammed = 0.0
            for e in appr:
                row = ps.get(e, {}).get(b)
                if not row:
                    continue
                tt, n, sp = row
                if n > 0 and sp < 0.35 * eidx[e]["speed"]:
                    jammed += eidx[e]["length"]
                ntt = ns.get(e, {}).get(b, (eidx[e]["length"] / max(eidx[e]["speed"], 1), 0, 0))[0]
                if n >= 3:
                    longest_wait = max(longest_wait, (tt - ntt) / 60)
            jam_len = max(jam_len, jammed)
        worst_b = max(per_b, key=per_b.get) if per_b else None
        junctions.append({
            "place": name, "extra_vehicle_hours": round(total, 1),
            "jammed_length_m": round(jam_len), "longest_extra_wait_min": round(longest_wait, 1),
            "worst_window": (f"{config.hhmm(worst_b)}-{config.hhmm(worst_b + config.EDGE_DATA_PERIOD)}"
                             if worst_b is not None else ""),
        })
    junctions.sort(key=lambda j: j["extra_vehicle_hours"], reverse=True)

    # ---- time to clear after the show (venue area = within 1.5 km) ----
    clear = {}
    for ev in scn.events:
        v = pl.get(ev.venue)
        if not v:
            continue
        vx, vy = v["xy"]
        area = [e for e in eidx if math.dist(network.edge_xy_mid(net, e), (vx, vy)) < 1500]
        end = config.parse_time(ev.show_end)
        series = defaultdict(float)
        for e in area:
            for b, val in interval_extra.get(e, {}).items():
                if b >= end - config.EDGE_DATA_PERIOD:
                    series[b] += val
        bs = sorted(series)
        peak = max([series[b] for b in bs] + [0])
        cleared_at = None
        threshold = max(0.1 * peak, 300)  # under 5 vehicle-minutes per 5 minutes counts as normal
        for i, b in enumerate(bs):
            if b <= end:
                continue
            if all(series[x] <= threshold for x in bs[i:i + 3]):
                cleared_at = b
                break
        clear[ev.name] = round((cleared_at - end) / 60) if cleared_at else round((config.parse_time(scn.sim_end) - end) / 60)

    # ---- parking (C2.7) ----
    dem = raw["demand"]
    arrivals = defaultdict(list)
    for k, v in pt.items():
        g = groups.get(k, "")
        if g.startswith("visitor|") and v[2]:
            lot = g.split("|", 1)[1]
            units = 0.25 if "_two" in k else 1.0
            arrivals[lot].append((v[4], units))
    parking = {}
    for lot, cap in dem["lot_capacity"].items():
        rows = sorted(arrivals.get(lot, []))
        cum, full_at = 0.0, None
        for t, u in rows:
            cum += u
            if full_at is None and cum >= 0.98 * cap:
                full_at = t
        parking[lot] = {"assigned": dem["lot_loads"].get(lot, 0), "capacity": cap,
                        "arrived": round(cum), "full_at": config.hhmm(full_at) if full_at else "not full"}

    return {
        "total_extra_vehicle_hours": round(extra_vh, 1),
        "visitor_avg_delay_min": round(st.mean(visitor) / 60, 1) if visitor else 0.0,
        "others_avg_extra_min": round(st.mean(others) / 60, 2) if others else 0.0,
        "ambulance": amb_out,
        "jumps": int(jumps), "jump_share_pct": round(100 * jumps / inserted, 2),
        "bottlenecks": junctions,
        "road_extra_min": road_extra,
        "edge_extra_vh": {e: round(v, 2) for e, v in edge_extra_vh.items() if abs(v) >= 0.05},
        "clear_minutes": clear,
        "parking": parking,
        "informal_parking": dem["informal_parking"],
        "redirected_from_full_lots": dem["redirected"],
        "walk_minutes_avg": dem["walk_minutes_avg"],
        "sensitive_closure_hours": _sensitive_closure_hours(plan, pl),
        "visitor_vehicles": dem["visitor_vehicles"],
    }


def combine(scn: Scenario, per_seed: list[dict]) -> dict:
    """Average the seeds and apply the hard rules."""
    def avg(key):
        return round(st.mean(m[key] for m in per_seed), 2)

    out = {k: avg(k) for k in ("total_extra_vehicle_hours", "visitor_avg_delay_min", "others_avg_extra_min",
                                "jump_share_pct", "informal_parking", "redirected_from_full_lots",
                                "walk_minutes_avg", "sensitive_closure_hours", "visitor_vehicles", "jumps")}

    amb = {}
    for hosp in per_seed[0]["ambulance"]:
        rows = [m["ambulance"][hosp] for m in per_seed if hosp in m["ambulance"]]
        worst = round(st.mean(r["worst_extra_min"] for r in rows), 1)
        amb[hosp] = {"normal_min": round(st.mean(r["normal_min"] for r in rows), 1),
                     "plan_min": round(st.mean(r["plan_min"] for r in rows), 1),
                     "worst_extra_min": worst,
                     "unfinished": sum(r["unfinished"] for r in rows),
                     "pass": worst <= scn.ambulance_limit_min and all(r["unfinished"] == 0 for r in rows)}
    out["ambulance"] = amb

    bn = defaultdict(list)
    for m in per_seed:
        for j in m["bottlenecks"]:
            bn[j["place"]].append(j)
    merged = []
    for place, rows in bn.items():
        merged.append({
            "place": place,
            "extra_vehicle_hours": round(st.mean(r["extra_vehicle_hours"] for r in rows), 1),
            "jammed_length_m": round(st.mean(r["jammed_length_m"] for r in rows)),
            "longest_extra_wait_min": round(st.mean(r["longest_extra_wait_min"] for r in rows), 1),
            "worst_window": max(rows, key=lambda r: r["extra_vehicle_hours"])["worst_window"],
        })
    merged.sort(key=lambda j: j["extra_vehicle_hours"], reverse=True)
    out["bottlenecks"] = merged[:5]
    out["all_junctions"] = merged

    keys = set().union(*(m["road_extra_min"] for m in per_seed))
    out["road_extra_min"] = {k: round(st.mean(m["road_extra_min"].get(k, 0) for m in per_seed), 1) for k in keys}
    out["clear_minutes"] = {k: round(st.mean(m["clear_minutes"][k] for m in per_seed))
                            for k in per_seed[0]["clear_minutes"]}
    out["parking"] = per_seed[0]["parking"]
    for lot in out["parking"]:
        fulls = [m["parking"][lot]["full_at"] for m in per_seed]
        out["parking"][lot]["full_at"] = sorted(fulls)[len(fulls) // 2]

    out["ambulance_pass"] = all(a["pass"] for a in amb.values()) if amb else True
    out["gridlock"] = out["jump_share_pct"] > 100 * config.GRIDLOCK_SHARE
    out["passes_hard_rules"] = out["ambulance_pass"] and not out["gridlock"]
    out["seeds"] = len(per_seed)
    return out


def headline(m: dict) -> dict:
    """The short set of numbers shown on plan cards and given to Gemma."""
    clear = max(m["clear_minutes"].values()) if m["clear_minutes"] else 0
    worst_amb = max((a["worst_extra_min"] for a in m["ambulance"].values()), default=0)
    return {
        "total_extra_vehicle_hours": m["total_extra_vehicle_hours"],
        "visitor_avg_delay_min": m["visitor_avg_delay_min"],
        "others_avg_extra_min": m["others_avg_extra_min"],
        "worst_ambulance_extra_min": worst_amb,
        "ambulance_pass": m["ambulance_pass"],
        "gridlock": m["gridlock"],
        "jump_share_pct": m["jump_share_pct"],
        "minutes_to_clear": clear,
        "sensitive_closure_hours": m["sensitive_closure_hours"],
        "walk_minutes_avg": m["walk_minutes_avg"],
        "informal_parking": m["informal_parking"],
    }


def rank_key(m: dict):
    """Hard rules first, then the main score, then the tie-breakers (docs/03)."""
    h = headline(m)
    return (0 if m["passes_hard_rules"] else 1, h["total_extra_vehicle_hours"],
            h["sensitive_closure_hours"], h["minutes_to_clear"], h["walk_minutes_avg"])
