---
name: event-traffic-rehearsal
description: Rehearse a city event's traffic plan in the SUMO simulator before the day. Use when asked to test or improve road closures, diversions and parking for a concert, match or festival in Chandigarh, compare plans, or draft a public traffic advisory in English, Hindi and Punjabi.
---

# Event traffic rehearsal

This skill drives the tools in this repository. It never touches real traffic systems and never
publishes anything; an officer approves every plan.

## Steps

1. Make sure the map exists: `data/network/chandigarh/places_resolved.json`. If not, run
   `python scripts/build_network.py`.
2. Write or load a scenario (`data/scenarios/*.json`, format in `sim/models.py`, `Scenario`) and a
   starting plan (`data/plans/*.json`, format `Plan`). Use only place names from `data/places.json`.
3. Run the rehearsal: `python scripts/run_demo.py --seeds 3`. It tests the starting plan, then up to
   4 improved plans, and writes `runs/<scenario id>/decision_log.md`.
4. Read `runs/<scenario id>/r*/metrics.json`. Report the plan that passes both hard rules
   (ambulance limit, no gridlock) with the lowest `total_extra_vehicle_hours`.
5. Show the officer `runs/<scenario id>/advisory.json` as a draft for approval in the app
   (`streamlit run app/main.py`, step 5).

## Rules

- Only use actions from `agent/menu.py` (`MENU_TEXT`) and names from the places list.
- At most 3 changes per round; at most 5 rounds and 15 simulation runs per rehearsal.
- Quote only numbers that appear in the run results.
- Never mark a plan approved yourself.
