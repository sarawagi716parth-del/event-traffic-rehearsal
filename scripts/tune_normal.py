"""Tune normal traffic (input B3) so a normal Saturday evening looks normal.

Runs the evening with no event for several trip totals and reports how busy the
roads are at 6-7 PM. Pick the largest total where main roads are busy but there
is no gridlock (stuck-vehicle jumps well under 1%, average speed on main roads
above about 60% of the limit). Record the value and why in docs/05-build-log.md
and set it in data/scenarios/*.json ("total_daily_trips").

    python scripts/tune_normal.py 80000 120000 160000
"""
from __future__ import annotations

import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ETR_NETWORK", "chandigarh")

from agent.menu import fill_scenario_defaults  # noqa: E402
from sim import network, runner  # noqa: E402
from sim.models import Scenario  # noqa: E402


def main():
    totals = [int(x) for x in sys.argv[1:]] or [80000, 120000, 160000]
    base = Scenario.model_validate_json((ROOT / "data/scenarios/diljit_2024-12-14.json").read_text())
    base, _ = fill_scenario_defaults(base)
    idx = network.load_index()["edges"]
    pr = sorted({e["priority"] for e in idx.values()})
    main_roads = {k for k, e in idx.items() if e["priority"] >= pr[int(len(pr) * 0.7)]}
    print(f"{'trips/day':>10} {'jumps %':>8} {'main-road speed % of limit, 18-19h':>36} {'wall s':>7}")
    for tot in totals:
        scn = base.model_copy(update={"normal": base.normal.model_copy(update={"total_daily_trips": tot})})
        d = ROOT / "runs" / "_tune" / str(tot)
        p = runner.run_many(runner.jobs_for(scn, None, d, [11]))[0]
        raw = runner.load_raw(p)
        ins = float(raw["stats"].get("vehicles", {}).get("inserted", 1))
        jumps = float(raw["stats"].get("teleports", {}).get("total", 0))
        ratios = []
        for eid, rows in raw["edges"].items():
            if eid in main_roads:
                for b, tt, n, sp in rows:
                    if 18 * 3600 <= b < 19 * 3600 and n > 0:
                        ratios.append(min(sp / max(idx[eid]["speed"], 1), 1.2))
        print(f"{tot:>10} {100 * jumps / ins:>8.2f} {100 * st.mean(ratios) if ratios else 0:>36.0f} "
              f"{raw['wall_seconds']:>7}")


if __name__ == "__main__":
    main()
