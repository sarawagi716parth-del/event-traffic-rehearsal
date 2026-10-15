"""Reading the road network and linking named places to it.

Everything here works on the SUMO network file. The heavy work (loading the
network, finding the connected part of it) is done once and cached in
`net_index.json`, so the app and the agent stay fast.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from . import config

config.find_sumo_home()
import sumolib  # noqa: E402  (needs SUMO_HOME first)

# Vehicle classes that ordinary traffic and visitors use
DRIVING_CLASS = "passenger"


@lru_cache(maxsize=4)
def load_net(name: str | None = None):
    path = config.net_file(name)
    if not path.exists():
        raise FileNotFoundError(
            f"Road network not found at {path}. Run scripts/build_network.py first."
        )
    return sumolib.net.readNet(str(path), withInternal=False)


def has_geo(net) -> bool:
    try:
        lon, lat = net.convertXY2LonLat(0, 0)
        return -180 <= lon <= 180 and -90 <= lat <= 90 and net.hasGeoProj()
    except Exception:
        return False


def to_xy(net, lat: float, lon: float):
    return net.convertLonLat2XY(lon, lat)


def to_lonlat(net, x: float, y: float):
    return net.convertXY2LonLat(x, y)


def _drivable(edge) -> bool:
    return edge.getFunction() == "" and edge.allows(DRIVING_CLASS)


def strongly_connected_edges(net) -> set[str]:
    """Edges from which a car can reach every other edge and come back.

    Trips are only created on these edges, so every simulated trip has a route.
    Uses an iterative Kosaraju search on the edge graph.
    """
    edges = [e for e in net.getEdges() if _drivable(e)]
    ids = {e.getID() for e in edges}
    succ = {e.getID(): [o.getID() for o in e.getOutgoing() if o.getID() in ids] for e in edges}
    pred: dict[str, list[str]] = {i: [] for i in ids}
    for a, outs in succ.items():
        for b in outs:
            pred[b].append(a)

    order, seen = [], set()
    for start in ids:
        if start in seen:
            continue
        stack = [(start, iter(succ[start]))]
        seen.add(start)
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                stack.pop()
                order.append(node)
            elif nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, iter(succ[nxt])))

    comp: dict[str, int] = {}
    best, best_size = None, 0
    for start in reversed(order):
        if start in comp:
            continue
        cid, size, stack = start, 0, [start]
        comp[start] = cid
        while stack:
            node = stack.pop()
            size += 1
            for p in pred[node]:
                if p not in comp:
                    comp[p] = cid
                    stack.append(p)
        if size > best_size:
            best, best_size = cid, size
    return {e for e, c in comp.items() if c == best}


def build_index(name: str | None = None) -> dict:
    """Summarise the network into a small JSON file used everywhere else."""
    net = load_net(name)
    good = strongly_connected_edges(net)
    geo = has_geo(net)
    edges = {}
    for e in net.getEdges():
        eid = e.getID()
        if eid not in good:
            continue
        shape = e.getShape()
        if geo:
            pts = [to_lonlat(net, x, y) for x, y in shape]
            pts = [[round(lat, 6), round(lon, 6)] for lon, lat in pts]
        else:
            pts = [[round(y, 1), round(x, 1)] for x, y in shape]
        edges[eid] = {
            "from": e.getFromNode().getID(),
            "to": e.getToNode().getID(),
            "length": round(e.getLength(), 1),
            "speed": round(e.getSpeed(), 2),
            "lanes": e.getLaneNumber(),
            "priority": e.getPriority(),
            "name": e.getName() or "",
            "shape": pts,
        }
    index = {"geo": geo, "edges": edges}
    out = config.network_dir(name) / "net_index.json"
    out.write_text(json.dumps(index))
    return index


@lru_cache(maxsize=4)
def load_index(name: str | None = None) -> dict:
    path = config.network_dir(name) / "net_index.json"
    if not path.exists():
        return build_index(name)
    return json.loads(path.read_text())


def edge_xy_mid(net, edge_id: str):
    shape = net.getEdge(edge_id).getShape()
    x = sum(p[0] for p in shape) / len(shape)
    y = sum(p[1] for p in shape) / len(shape)
    return x, y


def nearest_node(net, x: float, y: float, usable_edges: set[str], radius: float = 400):
    """Closest junction that a usable edge touches."""
    best, best_d = None, float("inf")
    for node in net.getNodes():
        touches = [e.getID() for e in node.getIncoming() + node.getOutgoing()]
        if not any(t in usable_edges for t in touches):
            continue
        nx, ny = node.getCoord()
        d = math.hypot(nx - x, ny - y)
        if d < best_d:
            best, best_d = node, d
    if best is None or best_d > radius:
        return None, best_d
    return best, best_d


def nearest_edges(net, x: float, y: float, usable_edges: set[str], k: int = 2, radius: float = 400):
    """The k closest usable edges to a point (used for lots, hospitals, entry points)."""
    found = net.getNeighboringEdges(x, y, radius)
    found = [(e, d) for e, d in found if e.getID() in usable_edges]
    found.sort(key=lambda t: t[1])
    return [(e.getID(), d) for e, d in found[:k]]


def shortest_path(net, from_node_id: str, to_node_id: str, usable_edges: set[str]):
    """Edges on the shortest drive from one junction to another."""
    a = net.getNode(from_node_id)
    b = net.getNode(to_node_id)
    best = None
    for start in a.getOutgoing():
        if start.getID() not in usable_edges:
            continue
        for end in b.getIncoming():
            if end.getID() not in usable_edges:
                continue
            path, cost = net.getShortestPath(start, end, vClass=DRIVING_CLASS)
            if path and (best is None or cost < best[1]):
                best = ([e.getID() for e in path], cost)
    return best[0] if best else []


def opposite_edges(net, edge_ids: list[str], usable_edges: set[str]) -> list[str]:
    """The other carriageway of a road: edges going the opposite way between the same junctions."""
    out = []
    for eid in edge_ids:
        e = net.getEdge(eid)
        for cand in e.getToNode().getOutgoing():
            if cand.getToNode() == e.getFromNode() and cand.getID() in usable_edges:
                out.append(cand.getID())
    return out


def upstream_edges(net, node_id: str, usable_edges: set[str], depth_m: float = 600) -> list[str]:
    """Edges feeding a junction, followed back up to `depth_m` metres.

    Used to measure queues at a named chowk or light point.
    """
    node = net.getNode(node_id)
    result, frontier = [], [(e, e.getLength()) for e in node.getIncoming()]
    seen = set()
    while frontier:
        edge, dist = frontier.pop()
        eid = edge.getID()
        if eid in seen or eid not in usable_edges:
            continue
        seen.add(eid)
        result.append(eid)
        if dist < depth_m:
            for prev in edge.getFromNode().getIncoming():
                frontier.append((prev, dist + prev.getLength()))
    return result


def fringe_edges(net, usable_edges: set[str], center, bearing=None, major_only=False, k=6) -> list[str]:
    """Entry roads at the edge of the map (where traffic from Mohali, Panchkula,
    Zirakpur and the highways comes in). `bearing` = [from, to] in degrees
    clockwise from north, seen from the map centre."""
    (x0, y0), (x1, y1) = net.getBBoxXY()
    margin = 400
    cands = []
    for eid in usable_edges:
        e = net.getEdge(eid)
        n = e.getFromNode()
        nx, ny = n.getCoord()
        if not (nx - x0 < margin or x1 - nx < margin or ny - y0 < margin or y1 - ny < margin):
            continue
        # entering edge: starts at the boundary node and heads inwards
        ex, ey = e.getToNode().getCoord()
        if math.hypot(ex - center[0], ey - center[1]) >= math.hypot(nx - center[0], ny - center[1]):
            continue
        b = (math.degrees(math.atan2(nx - center[0], ny - center[1])) + 360) % 360
        if bearing is not None:
            lo, hi = bearing
            if not (lo <= b <= hi if lo <= hi else (b >= lo or b <= hi)):
                continue
        cands.append((e.getPriority(), e.getLaneNumber(), eid))
    cands.sort(reverse=True)
    if major_only:
        top = cands[0][0] if cands else 0
        cands = [c for c in cands if c[0] >= top - 1]
    out = []
    for pr, ln, eid in cands[:k]:
        out.append(eid)
        back = opposite_edges(net, [eid], usable_edges)
        out += back[:1]
    return out


def distance_m(net, a_xy, b_xy) -> float:
    return math.hypot(a_xy[0] - b_xy[0], a_xy[1] - b_xy[1])
