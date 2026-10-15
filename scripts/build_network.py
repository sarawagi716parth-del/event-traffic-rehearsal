"""Builds the Chandigarh road network and places every named place on it.

Run once on the laptop (needs internet for the download):

    python scripts/build_network.py

If the download fails, open this link in a browser, save the file as
data/network/chandigarh/chandigarh.osm.xml, and run the script again with --offline:

    https://overpass-api.de/api/interpreter?data=<the query printed by --print-query>

Steps:
 1. Download roads, sector names, hospitals and named places from OpenStreetMap (Overpass API).
 2. Convert the roads into a SUMO network with netconvert.
 3. Find each named place in data/places_spec.json: by OpenStreetMap name, else from the sector grid.
 4. Apply hand fixes from data/places_manual.json.
 5. Link every place to the network and print a report.

Map data © OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim import config  # noqa: E402

NET_DIR = config.network_dir("chandigarh")
OSM_FILE = NET_DIR / "chandigarh.osm.xml"
SPEC = config.DATA / "places_spec.json"
MANUAL = config.DATA / "places_manual.json"
OUT = config.DATA / "places.json"

ROAD_TYPES = ("motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|"
              "tertiary|tertiary_link|unclassified|residential")


def overpass_query(b: dict) -> str:
    bb = f"{b['south']},{b['west']},{b['north']},{b['east']}"
    return (f'[out:xml][timeout:180];('
            f'way["highway"~"^({ROAD_TYPES})$"]({bb});'
            f'node["place"]["name"~"^Sector"]({bb});'
            f'nwr["amenity"="hospital"]({bb});'
            f'nwr["name"~"Chowk|Ground|Mandi|Market|Parking|Mandir|Vidyalaya|Mall|Polka|Dhanas|Faidan|Kajheri|'
            f'Gaushala|Majra|Niwas|Bhaskar|Exhibition",i]({bb});'
            f');(._;>;);out body;')


def download(b: dict):
    import requests

    NET_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading from OpenStreetMap (Overpass API). This can take 1-3 minutes...")
    for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
        try:
            r = requests.post(url, data={"data": overpass_query(b)}, timeout=300)
            if r.ok and b"<osm" in r.content[:500]:
                OSM_FILE.write_bytes(r.content)
                print(f"  saved {len(r.content) / 1e6:.1f} MB from {url}")
                return
            print(f"  {url} answered {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {url} failed: {exc}")
    raise SystemExit("Download failed. See the instructions at the top of this script for the browser route.")


def netconvert():
    print("Converting roads to a SUMO network (netconvert)...")
    args = [config.sumo_binary("netconvert"), "--osm-files", str(OSM_FILE),
            "-o", str(config.net_file("chandigarh")),
            "--geometry.remove", "true", "--roundabouts.guess", "true", "--ramps.guess", "true",
            "--junctions.join", "true", "--tls.guess-signals", "true", "--tls.discard-simple", "true",
            "--tls.join", "true", "--tls.default-type", "static",
            "--remove-edges.isolated", "true", "--keep-edges.by-vclass", "passenger",
            "--edges.join", "true", "--output.street-names", "true", "--output.original-names", "true",
            "--osm.elevation", "false", "--no-warnings", "true", "--proj.utm", "true"]
    subprocess.run(args, check=True)


def read_osm_features():
    """Named features and sector centres from the downloaded OSM file."""
    nodes, named, sectors, hospitals = {}, [], {}, []
    ways = []
    for _, el in ET.iterparse(OSM_FILE):
        if el.tag == "node":
            lat, lon = float(el.get("lat")), float(el.get("lon"))
            nodes[el.get("id")] = (lat, lon)
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            if tags:
                _collect(tags, (lat, lon), named, sectors, hospitals)
            el.clear()
        elif el.tag == "way":
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            name = tags.get("name", "")
            keep = name and ("highway" not in tags or tags.get("junction") == "roundabout"
                             or "chowk" in name.lower())
            if keep or tags.get("amenity") == "hospital":
                ways.append(([nd.get("ref") for nd in el.findall("nd")], tags))
            el.clear()
    for refs, tags in ways:
        pts = [nodes[r] for r in refs if r in nodes]
        if pts:
            c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            _collect(tags, c, named, sectors, hospitals)
    return named, sectors, hospitals


def _collect(tags, pos, named, sectors, hospitals):
    name = tags.get("name", "")
    if tags.get("place") and re.match(r"^Sector[\s-]*(\d+)", name):
        n = int(re.match(r"^Sector[\s-]*(\d+)", name).group(1))
        sectors.setdefault(n, pos)
    if tags.get("amenity") == "hospital" and name:
        hospitals.append((name, pos))
    if name:
        named.append((name, pos))


def mean(points):
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def locate(spec, named, sectors, venue_pos=None):
    """Returns ((lat, lon), how) or (None, reason)."""
    for key in spec.get("osm_names", []) or []:
        hits = [(n, pos) for n, pos in named if key.lower() in n.lower()]
        if hits:
            if venue_pos is not None and len(hits) > 1:
                hits.sort(key=lambda h: math.dist(h[1], venue_pos))
            return hits[0][1], f"OpenStreetMap name '{hits[0][0]}'"
    secs = spec.get("sectors")
    if secs:
        have = [sectors[s] for s in secs if s in sectors]
        if len(have) == len(secs):
            return mean(have), f"sector grid {'/'.join(map(str, secs))} (approximate)"
        return None, f"sector centres missing for {[s for s in secs if s not in sectors]}"
    if spec.get("beyond"):
        a, b = spec["beyond"]
        if a in sectors and b in sectors:
            pa, pb = sectors[a], sectors[b]
            return (pa[0] + (pa[0] - pb[0]) * 0.6, pa[1] + (pa[1] - pb[1]) * 0.6), \
                f"beyond sector {a} (approximate)"
    return None, "not found in OpenStreetMap; add it by hand"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use the OSM file already saved")
    ap.add_argument("--skip-netconvert", action="store_true", help="only re-place the named places")
    ap.add_argument("--print-query", action="store_true")
    args = ap.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    if args.print_query:
        print(overpass_query(spec["bbox"]))
        return
    if not args.offline and not args.skip_netconvert:
        download(spec["bbox"])
    if not OSM_FILE.exists():
        raise SystemExit(f"{OSM_FILE} is missing. Run without --offline first.")
    if not args.skip_netconvert:
        netconvert()

    named, sectors, hospitals = read_osm_features()
    print(f"Found {len(sectors)} sector names, {len(hospitals)} hospitals, {len(named)} named features")
    manual = json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}
    manual = {k: v for k, v in manual.items() if not k.startswith("_")}

    out, report = [], []
    venue_pos = None
    for p in spec["places"]:
        q = {k: v for k, v in p.items() if k not in ("osm_names", "sectors", "beyond")}
        if p["kind"] in ("road", "origin"):
            out.append(q)
            continue
        if p["name"] in manual:
            pos, how = tuple(manual[p["name"]]), "set by hand (places_manual.json)"
        else:
            pos, how = locate(p, named, sectors, venue_pos)
        if pos is None:
            report.append(f"  MISSING  {p['name']}: {how}")
            continue
        if p["kind"] == "venue" and venue_pos is None:
            venue_pos = pos
        q["lat"], q["lon"], q["found_by"] = round(pos[0], 6), round(pos[1], 6), how
        out.append(q)
        report.append(f"  ok       {p['name']}: {how}")

    # E1: protected hospitals near each venue, from OpenStreetMap (the officer confirms them)
    seen = set()
    for v in [x for x in out if x["kind"] == "venue" and "lat" in x]:
        near = sorted(hospitals, key=lambda h: math.dist(h[1], (v["lat"], v["lon"])))
        for name, pos in near:
            km = math.dist(pos, (v["lat"], v["lon"])) * 105
            if km > 3.0 or len([h for h in out if h.get("near") == v["name"]]) >= 5:
                break
            if name in seen:
                continue
            seen.add(name)
            out.append({"name": name, "kind": "hospital", "lat": round(pos[0], 6), "lon": round(pos[1], 6),
                        "near": v["name"], "found_by": "OpenStreetMap amenity=hospital", "aliases": []})
            report.append(f"  hospital {name} (~{km:.1f} km from {v['name']})")

    OUT.write_text(json.dumps({"about": spec["about"], "places": out}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print("\nNamed places:")
    print("\n".join(report))

    from sim import network, places

    network.load_net.cache_clear()
    network.load_index.cache_clear()
    print("\nIndexing the network (finding the connected road system)...")
    idx = network.build_index("chandigarh")
    print(f"  {len(idx['edges'])} usable road segments")
    places.load_places.cache_clear()
    res = places.resolve_places("chandigarh")
    print(f"\nLinked {len(res['places'])} places to the network.")
    if res["problems"]:
        print("Problems to fix (add positions to data/places_manual.json, then run with --skip-netconvert):")
        print("\n".join("  - " + x for x in res["problems"]))
    far = [(n, p.get("snap_m")) for n, p in res["places"].items() if (p.get("snap_m") or 0) > 150]
    if far:
        print("Places more than 150 m from the nearest road (check them on the map):")
        print("\n".join(f"  - {n}: {d} m" for n, d in far))
    print("\nDone. Next: python scripts/check_setup.py")


if __name__ == "__main__":
    main()
