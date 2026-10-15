"""Runs the whole demo without the app and saves the results the app shows.

    python scripts/run_demo.py                 # Sector 34 rehearsal + Sector 25 venue question
    python scripts/run_demo.py --brain rules   # without Gemma (fixed-rule stand-in)
    python scripts/run_demo.py --seeds 1       # faster, less reliable averages

Use this to compute results in advance (for example on Google Colab with a bigger
Gemma model) and then open the app: step 3 shows the saved rehearsal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ETR_NETWORK", "chandigarh")

from agent import report  # noqa: E402
from agent.brain import DEFAULT_MODEL, get_brain  # noqa: E402
from agent.loop import Agent, Budget  # noqa: E402
from agent.menu import check_plan, fill_scenario_defaults  # noqa: E402
from sim import config, metrics  # noqa: E402
from sim.models import Plan, Scenario  # noqa: E402
from sim.rehearsal import Rehearsal  # noqa: E402


def load(scn_path, plan_path):
    scn, notes = fill_scenario_defaults(Scenario.model_validate_json(Path(scn_path).read_text(encoding="utf-8")))
    plan, warns = check_plan(Plan.model_validate_json(Path(plan_path).read_text(encoding="utf-8")))
    for x in notes + warns:
        print("  note:", x)
    return scn, plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default="gemma", choices=["gemma", "rules"])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()
    seeds = config.DEFAULT_SEEDS[: args.seeds]
    brain = get_brain(args.brain, args.model)
    print(f"Brain: {brain.label}")
    if args.brain == "gemma" and brain.kind != "gemma":
        print("  Gemma is not reachable, so the fixed-rule stand-in is used. Start Ollama to use Gemma.")

    if config.NETWORK_NAME == "testgrid":
        d = config.network_dir("testgrid")
        cases = [(d / "scenario.json", d / "plan_police.json", True)]
    else:
        cases = [(ROOT / "data/scenarios/diljit_2024-12-14.json", ROOT / "data/plans/police_2024-12-14_sector34.json", True),
                 (ROOT / "data/scenarios/diljit_at_sector25.json", ROOT / "data/plans/police_2024-12-21_sector25.json", False)]

    summary = []
    for scn_path, plan_path, search in cases:
        scn, plan = load(scn_path, plan_path)
        print(f"\n=== {scn.title}")
        R = Rehearsal(scn, seeds=seeds)
        if search:
            for old in R.dir.glob("r[0-9][0-9]"):
                import shutil
                shutil.rmtree(old, ignore_errors=True)
            agent = Agent(R, brain, Budget(max_rounds=args.rounds),
                          on_event=lambda e: print("  ", e.get("text") or e["log"].result))
            out = agent.run(plan)
            best = out["best"]
            first = out["runs"][0]
            text, src = report.write_plan_summary(R, best, brain, compare_to=first)
            adv, asrc = report.draft_advisory(R, best, brain)
            (R.dir / "plan_summary.txt").write_text(text, encoding="utf-8")
            (R.dir / "advisory.json").write_text(json.dumps(adv, indent=1, ensure_ascii=False), encoding="utf-8")
            print("\nSummary:", text)
            summary.append((scn.title, R.compare(out["runs"])))
        else:
            rid = R.run_plan(plan, progress=lambda s: print("  ", s))
            summary.append((scn.title, R.compare([rid])))

    lines = ["# Demo results", "", f"Brain: {brain.label}. Seeds per plan: {len(seeds)}. Map: {config.NETWORK_NAME}.",
             "Numbers are from the simulation with the assumptions in the scenario files; use them to compare "
             "plans, not as predictions of exact jam lengths.", ""]
    for title, rows in summary:
        lines += [f"## {title}", "", "| Plan | Extra delay (veh-h) | Visitors (+min/trip) | Others (+min/trip) | "
                  "Worst ambulance (+min) | Clears after show (min) | Hard rules |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['plan']} | {r['total_extra_vehicle_hours']} | {r['visitor_avg_delay_min']} | "
                         f"{r['others_avg_extra_min']} | {r['worst_ambulance_extra_min']} | {r['minutes_to_clear']} | "
                         f"{'pass' if r['passes_hard_rules'] else 'FAIL'} |")
        lines.append("")
    out_md = ROOT / "docs" / "06-demo-results.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {out_md}")


if __name__ == "__main__":
    main()
