"""Runs SUMO for one plan and turns the raw output into a compact result file.

Runs use SUMO's mesoscopic mode (queues per road instead of every car's exact
position). It is many times faster than the detailed mode and is made for
comparing plans across a whole city, which is what the agent needs.
"""
from __future__ import annotations

import gzip
import json
import os
import pickle
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from . import config, demand, network, places
from .models import Plan, Scenario

config.find_sumo_home()


def _sumo_module():
    """libsumo is faster; traci works everywhere. Same commands for both."""
    if os.environ.get("ETR_USE_TRACI") != "1":
        try:
            import libsumo as sumo_api
            return sumo_api, True
        except Exception:
            pass
    import traci as sumo_api
    return sumo_api, False


def closure_events(scn: Scenario, plan: Plan | None, net_name: str | None = None):
    """Turn closures and diversions into (time, 'close'/'open', edges, allowed classes, label)."""
    if plan is None:
        return []
    pl = places.all_places(net_name)
    net = network.load_net(net_name)
    usable = set(network.load_index(net_name)["edges"])
    events = []

    def classes(allow):
        ok = set()
        for a in allow:
            ok.update(demand.ALLOW_TO_CLASSES.get(a, []))
        return sorted(ok)

    for c in plan.closures:
        road = pl.get(c.road)
        if not road or road["kind"] != "road":
            continue
        edges = []
        if c.direction in ("both", "forward"):
            edges += road["edges_forward"]
        if c.direction in ("both", "back"):
            edges += road.get("edges_back", [])
        events.append((config.parse_time(c.start), "close", edges, classes(c.allow), c.road))
        events.append((config.parse_time(c.end), "open", edges, [], c.road))

    for dv in plan.diversions:
        j, toward = pl.get(dv.junction), pl.get(dv.blocked_toward)
        if not j or not toward or "node" not in j:
            continue
        # Block the first stretch of road leaving the junction towards the blocked place
        target = toward.get("node")
        if target is None and toward.get("edges"):
            target = net.getEdge(toward["edges"][0]).getToNode().getID()
        path = network.shortest_path(net, j["node"], target, usable) if target else []
        if not path:
            continue
        first, length = [], 0.0
        for eid in path:
            first.append(eid)
            length += net.getEdge(eid).getLength()
            if length > 150:
                break
        label = f"Diversion at {dv.junction}"
        events.append((config.parse_time(dv.start), "close", first, classes(dv.allow), label))
        events.append((config.parse_time(dv.end), "open", first, [], label))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "open" else 1))
    return events


def _write_additional(path: Path, edge_out: Path):
    path.write_text(
        '<additional>\n'
        f'  <edgeData id="ed" file="{edge_out.name}" period="{config.EDGE_DATA_PERIOD}" '
        'excludeEmpty="true"/>\n'
        '</additional>\n', encoding="utf-8")


def run_one(job: dict) -> str:
    """Run one seed of one plan. Returns the path of the compact result file."""
    t_start = time.time()
    net_name = job.get("net")
    scn = Scenario.model_validate(job["scenario"])
    plan = Plan.model_validate(job["plan"]) if job.get("plan") else None
    seed = job["seed"]
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    dem = demand.build_demand(scn, plan, seed, include_event=plan is not None, net_name=net_name)
    routes = out_dir / "routes.xml"
    demand.write_routes(dem, routes, scn.rain)
    add = out_dir / "add.xml"
    edge_out = out_dir / "edgedata.xml"
    _write_additional(add, edge_out)
    trip_out = out_dir / "tripinfo.xml"
    stat_out = out_dir / "stats.xml"

    begin, end = config.parse_time(scn.sim_begin), config.parse_time(scn.sim_end)
    args = [
        config.sumo_binary("sumo"),
        "-n", str(config.net_file(net_name)), "-r", str(routes), "-a", str(add),
        "--begin", str(begin), "--end", str(end),
        "--mesosim", "true", "--meso-junction-control", "true",
        "--seed", str(seed),
        "--time-to-teleport", str(config.TIME_TO_TELEPORT),
        "--device.rerouting.probability", "1", "--device.rerouting.period", "300",
        "--device.rerouting.threads", str(max(1, min(4, (os.cpu_count() or 2) // 2))),
        "--device.rerouting.adaptation-interval", "10",
        "--routing-algorithm", "astar",
        "--tripinfo-output", str(trip_out), "--tripinfo-output.write-unfinished", "true",
        "--statistic-output", str(stat_out),
        "--ignore-route-errors", "true", "--no-step-log", "true", "--no-warnings", "true",
        "--duration-log.disable", "true",
    ]
    api, is_lib = _sumo_module()
    if is_lib:
        api.start(args)
    else:
        api.start(args, label=f"run{os.getpid()}")

    applied = []
    saved_allowed = {}
    for t, kind, edges, allow, label in closure_events(scn, plan, net_name):
        if t > begin:
            api.simulationStep(min(t, end))
        if t >= end:
            break
        lanes = []
        for eid in edges:
            try:
                n = api.edge.getLaneNumber(eid)
            except Exception:
                continue
            lanes += [f"{eid}_{i}" for i in range(n)]
        if kind == "close":
            blocked = [c for c in demand.ALL_ROAD_CLASSES if c not in allow]
            for ln in lanes:
                saved_allowed.setdefault(ln, api.lane.getAllowed(ln))
                api.lane.setDisallowed(ln, blocked)
            # Vehicles already on the way pick a new route at their next rerouting
            # check (every 2 minutes). Forcing it with rerouteTraveltime crashes
            # SUMO 1.28 in mesoscopic mode, so we don't.
        else:
            for ln in lanes:
                if ln in saved_allowed:
                    api.lane.setAllowed(ln, list(saved_allowed[ln]))
        applied.append({"time": config.hhmm(t), "what": kind, "label": label, "edges": len(edges)})
    api.simulationStep(end)
    api.close()

    raw = _compact(trip_out, edge_out, stat_out, dem)
    raw["seed"] = seed
    raw["applied"] = applied
    raw["wall_seconds"] = round(time.time() - t_start, 1)
    path = out_dir / "raw.pkl.gz"
    with gzip.open(path, "wb") as fh:
        pickle.dump(raw, fh)
    if not job.get("keep_xml"):
        for p in (routes, trip_out, edge_out):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                # Windows: SUMO can still hold a file for a moment after close(). The result
                # is already saved above, so a leftover XML file is harmless.
                pass
    return str(path)


def _compact(trip_out: Path, edge_out: Path, stat_out: Path, dem) -> dict:
    trips = {}
    for _, el in ET.iterparse(trip_out):
        if el.tag == "tripinfo":
            tid = el.get("id")
            arrival = float(el.get("arrival", -1))
            trips[tid] = (
                float(el.get("timeLoss", 0)),
                float(el.get("duration", 0)),
                arrival >= 0,
                float(el.get("depart", 0)),
                arrival,
            )
            el.clear()
    edges: dict[str, list] = {}
    index_speed = {}
    for _, el in ET.iterparse(edge_out):
        if el.tag == "interval":
            begin = float(el.get("begin"))
            for e in el.findall("edge"):
                eid = e.get("id")
                tt = e.get("traveltime")
                if tt is None:
                    continue
                edges.setdefault(eid, []).append(
                    (begin, float(tt), float(e.get("entered", 0)), float(e.get("speed", 0) or 0)))
            el.clear()
    stats = {}
    if stat_out.exists():
        root = ET.parse(stat_out).getroot()
        for child in root:
            stats[child.tag] = dict(child.attrib)
    return {"trips": trips, "edges": edges, "stats": stats,
            "demand": {
                "visitor_vehicles": dem.visitor_vehicles, "lot_loads": dem.lot_loads,
                "lot_capacity": dem.lot_capacity, "informal_parking": dem.informal_parking,
                "redirected": dem.redirected, "walk_minutes_avg": dem.walk_minutes_avg,
                "people_by_lot": dem.people_by_lot},
            "groups": dem.groups, "index_speed": index_speed}


def load_raw(path) -> dict:
    with gzip.open(path, "rb") as fh:
        return pickle.load(fh)


def run_many(jobs: list[dict], workers: int | None = None) -> list[str]:
    """Run several seeds or plans at the same time, each in its own process.

    Separate processes (python -m sim.worker) work the same way on Windows and
    Linux and inside Streamlit.
    """
    import subprocess
    import sys

    if workers is None:
        workers = int(os.environ.get("ETR_WORKERS", max(1, min(len(jobs), (os.cpu_count() or 2) - 1))))
    pending = list(enumerate(jobs))
    running, results, errors = [], [None] * len(jobs), []
    while pending or running:
        while pending and len(running) < workers:
            i, job = pending.pop(0)
            Path(job["out_dir"]).mkdir(parents=True, exist_ok=True)
            jf = Path(job["out_dir"]) / "job.json"
            jf.write_text(json.dumps(job), encoding="utf-8")
            log = open(Path(job["out_dir"]) / "worker.log", "w", encoding="utf-8")
            proc = subprocess.Popen([sys.executable, "-m", "sim.worker", str(jf)], cwd=str(config.ROOT),
                                    stdout=subprocess.PIPE, stderr=log, text=True)
            running.append((i, proc, log))
        time.sleep(0.5)
        for item in list(running):
            i, proc, log = item
            if proc.poll() is None:
                continue
            running.remove(item)
            out = proc.stdout.read().strip().splitlines()
            log.close()
            path = Path(jobs[i]["out_dir"]) / "raw.pkl.gz"
            if proc.returncode == 0 and path.exists():
                results[i] = str(path)
            else:
                tail = (Path(jobs[i]["out_dir"]) / "worker.log").read_text(encoding="utf-8")[-800:]
                errors.append(f"seed {jobs[i]['seed']}: exit {proc.returncode}: {tail}")
    if errors:
        raise RuntimeError("Simulation failed: " + " || ".join(errors))
    return results


def jobs_for(scn: Scenario, plan: Plan | None, run_dir: Path, seeds, net_name=None, keep_xml=False):
    return [{"scenario": scn.model_dump(), "plan": plan.model_dump() if plan else None,
             "seed": s, "out_dir": str(run_dir / f"seed{s}"), "net": net_name, "keep_xml": keep_xml}
            for s in seeds]


def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
