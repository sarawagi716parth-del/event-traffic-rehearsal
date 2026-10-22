# Next version plan (for the finale on 23 October)

Decided on 17 October 2026, after the first runs on the real Chandigarh map. Work in this order.
All work goes on the `finale` branch; `main` stays exactly as submitted.

## 1. Progress bar for every simulation

**Problem:** a run on the full map takes a long time and the screen shows nothing, so it looks frozen.

**Plan:**
- Each SUMO run reports the simulated clock (for example "18:40 of 01:00") and the number of
  vehicles on the road, every simulated 5 minutes, to a small progress file.
- The app reads these files and shows one bar per run plus an overall bar for the round, with an
  estimated time left.
- The command-line scripts print the same progress.

**Done when:** an officer can always see how far along a rehearsal is and roughly how long is left.

## 2. Shorter simulation time, on the full map

**Constraint:** keep every road segment (no dropping residential lanes) and keep accuracy.

**Facts so far:**
- One SUMO run uses one CPU core. SUMO cannot spread one run over several cores, and more RAM
  does not help. Splitting the map into pieces is not valid, because cars and jams cross the pieces.
- The speed has to come from doing less wasted work per run and running whole runs in parallel.

**Steps:**
1. Measure first with `scripts/time_one_run.py`: map loading, trip building, SUMO without
   rerouting, SUMO with rerouting. Fix the slowest part first.
2. Run whole simulations in parallel: seeds, candidate plans and the normal evening, up to
   (cores - 2) at once. Let the agent test 2 to 3 candidate plans per round side by side.
3. Rerouting: only vehicles affected by closures, diversions or event traffic re-plan; reroute
   every 5 minutes over several threads (already set: period 300 s, up to 4 threads).
4. Cache the normal evening per map and scenario, so it runs once, not once per rehearsal.
5. Simulate a shorter window (for example 15:00 to 24:00) with a warm-up period, if checks show
   the results don't change.
6. Quick "what if" questions run one seed first and report a provisional answer, then confirm.
7. Record the time per run on the laptop and the expected time on the pilot server (16 cores).

**Done when:** a full rehearsal on the full map finishes in a time an officer accepts, and the
measured times are written in the build log.

## 3. More realistic inputs (better accuracy)

- Normal traffic: tune the daily trip total and hourly curve (`scripts/tune_normal.py`) and record
  how it was checked.
- Where trips go: weight trip ends towards markets, offices, the industrial area and coaching
  centres instead of a random spread.
- Vehicle mix from Chandigarh registration data (Vahan), adjusted for vehicles actually on the road.
- Traffic from Mohali, Panchkula and Zirakpur at the right entry roads (fix the missing Mohali entry).
- Fix the named places the map build could not find (New Labour Chowk, Gaushala Chowk, South End
  Chowk, Gurudwara Chowk, Sham Mall T-point, Polka turn, Yatri Niwas Chowk, Sector 14/15/24/25 Chowk)
  in `data/places_manual.json`.
- Real signal timings, if the traffic police can share them.
- Sanity check: Plan A should show trouble at Piccadilly Chowk, New Labour Chowk and the Sector 32
  junction, as reported in December 2024.

## 4. New outputs for the officer

- **Safe crowd limit:** rerun the best plan at 15,000 / 20,000 / 25,000 / 30,000 / 35,000 people and
  report the largest crowd where ambulances stay within the limit and nothing gridlocks, with the
  first thing that fails above it (for example "ambulance access to Bedi Hospital").
- **Maximum vehicles:** the same search expressed as the number of event vehicles the road network
  and parking can take for that plan.
- **Road-by-road capacity use:** for the main roads near the venue, the peak traffic as a share of
  what the road carried before it jammed.
- Later: the Sarangpur venue rehearsal (35,000 people, 6,250 parking spaces).

## 5. Other items already listed in the docs

- Several events on one day; rallies and VIP convoys as moving closures (docs/03, Finals).
- UX4G front end, logins with roles, audit trail (docs/00).
- Shuttle and staggered-exit actions (docs/03, If time).
