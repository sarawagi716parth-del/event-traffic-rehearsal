"""The named places list: the only names the agent and the plans may use.

`data/places.json` holds human-readable places (chowks, light points, roads,
parking grounds, hospitals, the venue and the directions visitors come from)
with map positions. `resolve_places()` links each one to the SUMO network and
saves `places_resolved.json` next to the network.
"""
from __future__ import annotations

import json
from functools import lru_cache

from rapidfuzz import fuzz, process

from . import config, network

KINDS = ("junction", "road", "parking", "hospital", "venue", "origin")


@lru_cache(maxsize=4)
def load_places(name: str | None = None) -> dict:
    return json.loads(config.places_file(name).read_text(encoding="utf-8"))


def resolve_places(name: str | None = None) -> dict:
    """Link every named place to the network. Writes a report of anything that failed."""
    net = network.load_net(name)
    index = network.load_index(name)
    usable = set(index["edges"])
    raw = load_places(name)
    resolved, problems = {}, []

    def xy_of(p):
        if index["geo"]:
            return network.to_xy(net, p["lat"], p["lon"])
        return p["x"], p["y"]

    # Points first (everything except roads)
    for p in raw["places"]:
        if p["kind"] == "road":
            continue
        entry = dict(p)
        x, y = xy_of(p)
        entry["xy"] = [round(x, 1), round(y, 1)]
        if p["kind"] in ("junction", "venue"):
            radius = 1500 if p["kind"] == "venue" else 400  # a ground sits inside a block
            node, dist = network.nearest_node(net, x, y, usable, radius=radius)
            if node is None:
                problems.append(f"{p['name']}: no junction within 400 m (nearest {dist:.0f} m)")
                continue
            entry["node"] = node.getID()
            entry["snap_m"] = round(dist, 1)
        if p["kind"] in ("parking", "hospital", "venue", "origin"):
            k = 3 if p["kind"] == "origin" else 2
            near = network.nearest_edges(net, x, y, usable, k=k, radius=600)
            if not near:
                problems.append(f"{p['name']}: no road within 600 m")
                continue
            entry["edges"] = [e for e, _ in near]
            entry["snap_m"] = round(near[0][1], 1)
        resolved[p["name"]] = entry

    # Roads: shortest drive between two named junctions, both directions
    for p in raw["places"]:
        if p["kind"] != "road":
            continue
        a, b = resolved.get(p["from"]), resolved.get(p["to"])
        if not a or not b or "node" not in a or "node" not in b:
            problems.append(f"{p['name']}: end junction missing ({p['from']} / {p['to']})")
            continue
        fwd = network.shortest_path(net, a["node"], b["node"], usable)
        back = network.shortest_path(net, b["node"], a["node"], usable)
        if not fwd:
            problems.append(f"{p['name']}: no drivable path from {p['from']} to {p['to']}")
            continue
        entry = dict(p)
        entry["edges_forward"] = fwd
        entry["edges_back"] = back
        entry["length_m"] = round(sum(index["edges"][e]["length"] for e in fwd), 1)
        entry["xy"] = [round((a["xy"][0] + b["xy"][0]) / 2, 1), round((a["xy"][1] + b["xy"][1]) / 2, 1)]
        resolved[p["name"]] = entry

    # Queue-measuring edges for every junction
    for entry in resolved.values():
        if entry["kind"] in ("junction", "venue") and "node" in entry:
            entry["approach_edges"] = network.upstream_edges(net, entry["node"], usable)

    # Distance from the venue for every place (the map summary the agent reads)
    venues = [v for v in resolved.values() if v["kind"] == "venue"]
    for entry in resolved.values():
        entry["dist_from_venue_km"] = {
            v["name"]: round(network.distance_m(net, entry["xy"], v["xy"]) / 1000, 2) for v in venues
        }

    out = {"network": name or config.NETWORK_NAME, "places": resolved, "problems": problems}
    config.resolved_places_file(name).write_text(json.dumps(out, indent=1), encoding="utf-8")
    load_resolved.cache_clear()
    return out


@lru_cache(maxsize=4)
def load_resolved(name: str | None = None) -> dict:
    path = config.resolved_places_file(name)
    if not path.exists():
        return resolve_places(name)
    return json.loads(path.read_text(encoding="utf-8"))


def all_places(name: str | None = None) -> dict:
    return load_resolved(name)["places"]


def names(kind: str | None = None, name: str | None = None) -> list[str]:
    return [n for n, p in all_places(name).items() if kind is None or p["kind"] == kind]


def _alias_table(name: str | None = None) -> dict[str, str]:
    table = {}
    for n, p in all_places(name).items():
        table[n.lower()] = n
        for a in p.get("aliases", []):
            table[a.lower()] = n
    return table


def match(text: str, kind: str | tuple | None = None, name: str | None = None,
          threshold: int = 85) -> str | None:
    """Turn a name written by a person or by Gemma into an exact place name.

    Small spelling differences ("Picadilly") are accepted. Anything else returns
    None, so the caller can reject it.
    """
    if not text:
        return None
    kinds = (kind,) if isinstance(kind, str) else kind
    table = _alias_table(name)
    places = all_places(name)
    allowed = {k: v for k, v in table.items() if kinds is None or places[v]["kind"] in kinds}
    key = str(text).strip().lower()
    if key in allowed:
        return allowed[key]
    best = process.extractOne(key, list(allowed), scorer=fuzz.WRatio)
    if best and best[1] >= threshold:
        return allowed[best[0]]
    return None


def map_summary(name: str | None = None, max_chars: int = 3500) -> str:
    """A short text description of the named places, for Gemma's prompt."""
    lines = []
    for n, p in all_places(name).items():
        d = p.get("dist_from_venue_km", {})
        dist = ", ".join(f"{km} km from {v}" for v, km in d.items()) if d else ""
        if p["kind"] == "parking":
            lines.append(f"- PARKING {n}: about {p.get('capacity', '?')} cars; {dist}")
        elif p["kind"] == "road":
            lines.append(f"- ROAD {n}: from {p['from']} to {p['to']}, {p.get('length_m', 0)/1000:.1f} km"
                         + (" (market/residential)" if p.get("sensitive_area") else ""))
        elif p["kind"] == "junction":
            lines.append(f"- JUNCTION {n}; {dist}")
        elif p["kind"] == "hospital":
            lines.append(f"- HOSPITAL {n}; {dist}")
        elif p["kind"] == "origin":
            lines.append(f"- ORIGIN {n} (where visitors come from)")
        elif p["kind"] == "venue":
            lines.append(f"- VENUE {n}")
    text = "\n".join(lines)
    return text[:max_chars]
