"""Checks that everything needed for the demo is in place, and says what to fix.

    python scripts/check_setup.py            # all checks
    python scripts/check_setup.py --no-sim   # skip the 1-run simulation test
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK, BAD, WARN = "[ ok ]", "[FAIL]", "[warn]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--model", default=os.environ.get("ETR_MODEL", "gemma4:e4b-it-qat"))
    args = ap.parse_args()
    problems = 0

    print(f"Python {sys.version.split()[0]}")
    for mod in ("sumolib", "traci", "pydantic", "pandas", "streamlit", "folium", "streamlit_folium",
                "rapidfuzz", "ollama", "pyproj", "holidays"):
        try:
            __import__(mod)
            print(OK, mod)
        except Exception as exc:  # noqa: BLE001
            print(BAD, mod, "->", exc, "  fix: pip install -r requirements.txt")
            problems += 1
    try:
        import libsumo  # noqa: F401
        print(OK, "libsumo (fast runs)")
    except Exception:
        print(WARN, "libsumo not available; traci will be used (slower but works). To force: set ETR_USE_TRACI=1")

    from sim import config

    try:
        home = config.find_sumo_home()
        print(OK, "SUMO_HOME =", home)
    except Exception as exc:  # noqa: BLE001
        print(BAD, exc)
        problems += 1

    net = config.net_file("chandigarh")
    if net.exists() and config.resolved_places_file("chandigarh").exists():
        import json

        res = json.loads(config.resolved_places_file("chandigarh").read_text(encoding="utf-8"))
        print(OK, f"Chandigarh map built; {len(res['places'])} named places linked")
        for p in res["problems"]:
            print(WARN, "  ", p)
    else:
        print(BAD, "Chandigarh map not built yet. Run: python scripts/build_network.py")
        problems += 1

    from agent.brain import OllamaBrain

    ok, msg = OllamaBrain.available(args.model)
    print(OK if ok else BAD, "Gemma:", msg)
    if ok:
        from agent.schemas import TextDraft

        t = time.time()
        try:
            b = OllamaBrain(args.model)
            d, retries = b.ask("Reply in JSON.", 'Say hello to a traffic officer. JSON: {"text": "..."}', TextDraft)
            print(OK, f"Gemma answered in the fixed JSON format in {time.time() - t:.1f} s: {d.text[:60]!r}")
        except Exception as exc:  # noqa: BLE001
            print(BAD, "Gemma did not return valid JSON:", exc)
            problems += 1
    else:
        print("      fix: install Ollama, then: ollama pull", args.model)
        problems += 1

    if not args.no_sim and net.exists():
        os.environ["ETR_NETWORK"] = "chandigarh"
        from agent.menu import check_plan, fill_scenario_defaults
        from sim import metrics
        from sim.models import Plan, Scenario
        from sim.rehearsal import Rehearsal

        scn = Scenario.model_validate_json((ROOT / "data/scenarios/diljit_2024-12-14.json").read_text())
        scn, notes = fill_scenario_defaults(scn)
        for n in notes:
            print(WARN, n)
        plan, warns = check_plan(Plan.model_validate_json(
            (ROOT / "data/plans/police_2024-12-14_sector34.json").read_text()))
        for w in warns:
            print(WARN, w)
        print("Running Plan A once (1 seed) to time the simulation...")
        t = time.time()
        R = Rehearsal(scn, seeds=[11])
        rid = R.run_plan(plan, progress=lambda s: print("      ", s))
        h = metrics.headline(R.results(rid))
        print(OK, f"Simulation works: normal evening + Plan A in {time.time() - t:.0f} s")
        print("      ", h)
        print("      Worst places:", [b["place"] for b in R.results(rid)["bottlenecks"]])
    print("\nAll good." if problems == 0 else f"\n{problems} thing(s) to fix above.")


if __name__ == "__main__":
    main()
