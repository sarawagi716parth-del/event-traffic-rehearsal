"""Maps for the app: a preview of the named places and the delay map of a plan."""
from __future__ import annotations

import folium

from sim import network, places

# Delay buckets: colour plus text, so the map also works for colour-blind users
BUCKETS = [(1, "#9AA5B1", "under 1 min"), (3, "#E3B341", "1-3 min"), (10, "#E07B24", "3-10 min"),
           (1e9, "#B42318", "over 10 min")]
KIND_STYLE = {"venue": ("#123E7C", "star"), "parking": ("#1E7B47", "car"), "hospital": ("#B42318", "plus"),
              "junction": ("#5B6675", "circle")}


def _center(pl):
    pts = [(p["lat"], p["lon"]) for p in pl.values() if "lat" in p]
    if not pts:
        return 30.73, 76.78
    return sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts)


def _base(pl, zoom=14):
    m = folium.Map(location=_center(pl), zoom_start=zoom, tiles="OpenStreetMap", control_scale=True,
                   attr="© OpenStreetMap contributors")
    return m


def _edge_line(index, eid):
    return index["edges"][eid]["shape"]


def preview_map(venue: str | None, lots: list[str], hospitals: list[str], plan=None):
    pl = places.all_places()
    index = network.load_index()
    m = _base({k: v for k, v in pl.items() if k in (lots + hospitals + [venue or ""])} or pl, zoom=13)
    if plan is not None:
        for c in plan.closures:
            road = pl.get(c.road)
            if road:
                for e in road["edges_forward"]:
                    folium.PolyLine(_edge_line(index, e), color="#123E7C", weight=6, dash_array="8,6",
                                    tooltip=f"Closed {c.start}-{c.end}: {c.road}").add_to(m)
    for name, p in pl.items():
        if "lat" not in p:
            continue
        kind = p["kind"]
        if kind == "parking" and name not in lots:
            color = "#9AA5B1"
        elif kind == "hospital" and name not in hospitals:
            continue
        else:
            color = KIND_STYLE.get(kind, ("#5B6675", "circle"))[0]
        label = name
        if kind == "parking":
            label += f" (about {p.get('capacity', '?')} cars{'' if name in lots else ', not used'})"
        if p.get("found_by"):
            label += f" | position: {p['found_by']}"
        radius = 9 if kind in ("venue", "parking", "hospital") else 5
        folium.CircleMarker((p["lat"], p["lon"]), radius=radius, color=color, fill=True, fill_opacity=0.85,
                            tooltip=label).add_to(m)
    return m


def delay_map(metrics: dict, plan, top_n_context: int = 2500):
    """Roads coloured by the worst extra wait per vehicle in any 5-minute window."""
    pl = places.all_places()
    index = network.load_index()
    m = _base(pl, zoom=14)
    # light context: the bigger roads
    big = sorted(index["edges"].items(), key=lambda kv: (kv[1]["priority"], kv[1]["lanes"]), reverse=True)
    for eid, e in big[:top_n_context]:
        folium.PolyLine(e["shape"], color="#CBD2D9", weight=2, opacity=0.7).add_to(m)
    for eid, minutes in sorted(metrics.get("road_extra_min", {}).items(), key=lambda kv: kv[1]):
        if eid not in index["edges"] or minutes < 0.5:
            continue
        color = next(c for lim, c, _ in BUCKETS if minutes < lim)
        name = index["edges"][eid]["name"] or "road"
        folium.PolyLine(index["edges"][eid]["shape"], color=color, weight=5 if minutes >= 3 else 3,
                        opacity=0.9, tooltip=f"{name}: up to +{minutes} min").add_to(m)
    if plan is not None:
        for c in plan.closures:
            road = pl.get(c.road)
            if road:
                for e in road["edges_forward"]:
                    folium.PolyLine(_edge_line(index, e), color="#123E7C", weight=6, dash_array="8,6",
                                    tooltip=f"Closed {c.start}-{c.end}: {c.road}").add_to(m)
        for lot in plan.open_lots():
            p = pl.get(lot)
            if p and "lat" in p:
                folium.CircleMarker((p["lat"], p["lon"]), radius=8, color="#1E7B47", fill=True,
                                    tooltip=f"Parking: {lot}").add_to(m)
    for b in metrics.get("bottlenecks", [])[:5]:
        p = pl.get(b["place"])
        if p and "lat" in p:
            folium.Marker((p["lat"], p["lon"]),
                          tooltip=f"{b['place']}: queue {b['jammed_length_m']} m, wait +{b['longest_extra_wait_min']} "
                                  f"min at {b['worst_window']}",
                          icon=folium.Icon(color="red", icon="exclamation-sign")).add_to(m)
    return m


def legend_html() -> str:
    items = "".join(f'<span><i style="background:{c}"></i>{t}</span>' for _, c, t in BUCKETS)
    return (f'<div class="etr-legend">Extra wait per vehicle: {items}'
            '<span><i style="background:#123E7C"></i>closed road (dashed)</span></div>')
