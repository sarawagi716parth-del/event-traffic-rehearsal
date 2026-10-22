"""Times one normal-evening run on the full map, split into its parts.

    python scripts/time_one_run.py 30000
"""
import os, sys, time, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.environ.setdefault("ETR_NETWORK", "chandigarh")
from agent.menu import fill_scenario_defaults
from sim import config, demand, network
from sim.models import Scenario

trips = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
scn, _ = fill_scenario_defaults(Scenario.model_validate_json((ROOT / "data/scenarios/diljit_2024-12-14.json").read_text()))
scn = scn.model_copy(update={"normal": scn.normal.model_copy(update={"total_daily_trips": trips})})
d = demand.build_demand(scn, None, 11, include_event=False)
out = ROOT / "runs" / "_timing"; out.mkdir(parents=True, exist_ok=True)
demand.write_routes(d, out / "routes.xml")
net = str(config.net_file())
print(f"map file: {os.path.getsize(net)/1e6:.0f} MB")
base = [config.sumo_binary("sumo"), "-n", net, "--mesosim", "true", "--time-to-teleport", "600",
        "--ignore-route-errors", "true", "--no-step-log", "true", "--no-warnings", "true"]
tests = [
    ("A. load the map only (1 simulated second)", ["--begin", "46800", "--end", "46801"]),
    ("B. 1 simulated hour, no trips at all", ["--begin", "46800", "--end", "50400"]),
    ("C. 1 simulated hour with trips, junction control ON", ["-r", str(out / "routes.xml"), "--begin", "46800",
        "--end", "50400", "--meso-junction-control", "true", "--device.rerouting.probability", "0"]),
    ("D. 1 simulated hour with trips, junction control OFF", ["-r", str(out / "routes.xml"), "--begin", "46800",
        "--end", "50400", "--meso-junction-control", "false", "--device.rerouting.probability", "0"]),
]
for label, extra in tests:
    t = time.time(); r = subprocess.run(base + extra, capture_output=True, text=True)
    print(f"{label}: {time.time()-t:.0f} s" + ("" if r.returncode == 0 else f"  (error: {r.stderr[-200:]})"))
