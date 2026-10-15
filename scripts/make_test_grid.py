"""Builds a small stand-in grid map for testing the code without the real map.

This is NOT Chandigarh. It is a 6 x 5 block grid placed at a made-up spot, with
generic names (Test Chowk B2, Test Lot East ...). Use it only to check that the
simulation, the agent and the app work. Results on it mean nothing for the city.

    python scripts/make_test_grid.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim import config  # noqa: E402

OUT = config.network_dir("testgrid")
LAT0, LON0 = 30.70, 76.75        # only so the map widget has somewhere to draw
M_LAT, M_LON = 1 / 110900, 1 / 95700
COLS, ROWS, DX, DY = 6, 5, 800, 1200


def ll(x, y):
    return round(LAT0 + y * M_LAT, 6), round(LON0 + x * M_LON, 6)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    nodes, edges = [], []
    for c in range(COLS + 1):
        for r in range(ROWS + 1):
            lat, lon = ll(c * DX, r * DY)
            tl = (c + r) % 2 == 0 and 0 < c < COLS and 0 < r < ROWS
            nodes.append(f'<node id="n{c}_{r}" x="{lon}" y="{lat}" type="{"traffic_light" if tl else "priority"}"/>')
    # Entry stubs: west (like Mohali), east (like Panchkula), south (like Zirakpur)
    stubs = {"W": (-1000, 2 * DY, "n0_2"), "E": (COLS * DX + 1000, 3 * DY, f"n{COLS}_3"),
             "S": (4 * DX, -1000, "n4_0")}
    for k, (x, y, _) in stubs.items():
        lat, lon = ll(x, y)
        nodes.append(f'<node id="stub{k}" x="{lon}" y="{lat}" type="priority"/>')

    def road(a, b, lanes, speed):
        edges.append(f'<edge id="{a}to{b}" from="{a}" to="{b}" numLanes="{lanes}" speed="{speed}"/>')
        edges.append(f'<edge id="{b}to{a}" from="{b}" to="{a}" numLanes="{lanes}" speed="{speed}"/>')

    for c in range(COLS + 1):
        for r in range(ROWS + 1):
            arterial_v = c in (2, 4)
            arterial_h = r in (2,)
            if c < COLS:
                road(f"n{c}_{r}", f"n{c + 1}_{r}", 2 if arterial_h else 1, 16.7 if arterial_h else 13.9)
            if r < ROWS:
                road(f"n{c}_{r}", f"n{c}_{r + 1}", 2 if arterial_v else 1, 16.7 if arterial_v else 13.9)
    for k, (_, _, n) in stubs.items():
        road(f"stub{k}", n, 2, 22.2)

    (OUT / "grid.nod.xml").write_text("<nodes>\n" + "\n".join(nodes) + "\n</nodes>\n")
    (OUT / "grid.edg.xml").write_text("<edges>\n" + "\n".join(edges) + "\n</edges>\n")
    subprocess.run([config.sumo_binary("netconvert"), "-n", str(OUT / "grid.nod.xml"),
                    "-e", str(OUT / "grid.edg.xml"), "--proj.utm", "true",
                    "--no-turnarounds.except-deadend", "true", "--tls.default-type", "static",
                    "-o", str(config.net_file("testgrid")), "--no-warnings", "true"], check=True)

    def jn(name, c, r, **kw):
        lat, lon = ll(c * DX, r * DY)
        return {"name": name, "kind": "junction", "lat": lat, "lon": lon, **kw}

    def pt(name, kind, x, y, **kw):
        lat, lon = ll(x, y)
        return {"name": name, "kind": kind, "lat": lat, "lon": lon, **kw}

    pl = [
        pt("Test Venue Ground", "venue", 3.5 * DX, 2.5 * DY),
        jn("Test Chowk C2", 3, 2), jn("Test Chowk D2", 4, 2), jn("Test Chowk C3", 3, 3),
        jn("Test Chowk D3", 4, 3), jn("Test Chowk B2", 2, 2), jn("Test Chowk E2", 5, 2),
        jn("Test Chowk C1", 3, 1), jn("Test Chowk D4", 4, 4), jn("Test Chowk A2", 0, 2),
        jn("Test Chowk F3", 6, 3), jn("Test Chowk E0", 4, 0),
        {"name": "Test Venue Road", "kind": "road", "from": "Test Chowk C2", "to": "Test Chowk D2",
         "sensitive_area": True},
        {"name": "Test Market Road", "kind": "road", "from": "Test Chowk C3", "to": "Test Chowk D3",
         "sensitive_area": True},
        {"name": "Test Middle Avenue", "kind": "road", "from": "Test Chowk B2", "to": "Test Chowk E2"},
        pt("Test Lot North", "parking", 3.5 * DX, 4.0 * DY, capacity=1500),
        pt("Test Lot West", "parking", 1.5 * DX, 2.0 * DY, capacity=1200),
        pt("Test Lot East", "parking", 5.5 * DX, 3.0 * DY, capacity=1200),
        pt("Test Lot South", "parking", 4.0 * DX, 0.5 * DY, capacity=1000),
        pt("Test Hospital A", "hospital", 2.5 * DX, 3.0 * DY),
        pt("Test Hospital B", "hospital", 4.5 * DX, 2.0 * DY),
        pt("Test City", "origin", 3 * DX, 2.5 * DY, interior=True),
        pt("Test West Town", "origin", -1000, 2 * DY),
        pt("Test East Town", "origin", COLS * DX + 1000, 3 * DY),
        pt("Test South Town", "origin", 4 * DX, -1000),
    ]
    (OUT / "places.json").write_text(json.dumps({"note": "Stand-in test grid, not Chandigarh",
                                                 "places": pl}, indent=1))
    print("Test grid written to", OUT)


if __name__ == "__main__":
    main()
