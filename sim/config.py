"""Shared paths and settings for the simulation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RUNS = ROOT / "runs"

# Which map to use. "chandigarh" is the real map built from OpenStreetMap by
# scripts/build_network.py. "testgrid" is a small stand-in grid used only for
# testing the code when the real map is not available.
NETWORK_NAME = os.environ.get("ETR_NETWORK", "chandigarh")


def network_dir(name: str | None = None) -> Path:
    return DATA / "network" / (name or NETWORK_NAME)


def net_file(name: str | None = None) -> Path:
    return network_dir(name) / "city.net.xml"


def places_file(name: str | None = None) -> Path:
    """The named places list for a map. The test grid has its own list."""
    n = name or NETWORK_NAME
    if n == "chandigarh":
        return DATA / "places.json"
    return network_dir(n) / "places.json"


def resolved_places_file(name: str | None = None) -> Path:
    return network_dir(name) / "places_resolved.json"


def find_sumo_home() -> str:
    """Find SUMO, whether it came from the Windows installer or from pip."""
    home = os.environ.get("SUMO_HOME")
    if home and Path(home).exists():
        return home
    try:
        import sumo  # installed by `pip install eclipse-sumo`

        os.environ["SUMO_HOME"] = sumo.SUMO_HOME
        return sumo.SUMO_HOME
    except ImportError as exc:
        raise RuntimeError(
            "SUMO not found. Install it (see README) and set SUMO_HOME."
        ) from exc


def sumo_binary(name: str = "sumo") -> str:
    home = Path(find_sumo_home())
    exe = name + (".exe" if sys.platform.startswith("win") else "")
    path = home / "bin" / exe
    return str(path) if path.exists() else name


# Simulation defaults (see docs/01-simulation-inputs.md, section G)
SIM_BEGIN = 13 * 3600          # 1 PM
SIM_END = 25 * 3600            # 1 AM next day
EDGE_DATA_PERIOD = 300         # delay on every road every 5 minutes
TIME_TO_TELEPORT = 600         # stuck vehicles wait 10 minutes before a jump
GRIDLOCK_SHARE = 0.01          # more than 1% jumps means gridlock
DEFAULT_SEEDS = [11, 22, 33]


def hhmm(seconds: float) -> str:
    """46800 -> '13:00'. Times after midnight show as 24:xx so order stays clear."""
    s = int(round(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}"


def parse_time(value) -> int:
    """Accepts '16:00', '4 PM', '4:30 pm', '24:30' or seconds. Returns seconds of day."""
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(".", ":")
    pm = text.endswith("pm")
    am = text.endswith("am")
    text = text.replace("pm", "").replace("am", "").strip()
    parts = text.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    if pm and hour < 12:
        hour += 12
    if am and hour == 12:
        hour = 24  # 12 AM at night, after an evening event
    return hour * 3600 + minute * 60
