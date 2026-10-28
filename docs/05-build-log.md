# Build log: decisions made while building

Started 16 October 2026. Newest entries at the bottom. Each entry: what we decided, why, and what it changes.

## 1. Mesoscopic SUMO instead of the detailed mode

- **Decision:** every run uses SUMO's mesoscopic mode (`--mesosim`, with junction control on).
- **Why:** the agent needs up to 15 runs per rehearsal, each covering 1 PM to 1 AM across the whole city.
  The detailed mode tracks every car's exact position and would take far longer per run on the laptop.
  Meso models queues per road, which is what we need to compare plans.
- **Effect:** "longest queue" is reported as the **jammed length**: the total length of roads feeding a
  junction where traffic moves at under 35% of the speed limit, in the worst 5-minute window.

## 2. Closures through lane permissions, rerouting every 2 minutes

- **Decision:** a closure changes who may use each lane of the road (`lane.setDisallowed`) at its start
  time and restores it at its end. Every vehicle has SUMO's rerouting device and looks for a better
  route every 2 minutes, so traffic finds its way around closures.
- **Why:** forcing an immediate reroute (`vehicle.rerouteTraveltime`) crashes SUMO 1.28 in meso mode.
  We found this in testing.
- **Who may pass:** visitors' cars and two-wheelers use their own vehicle class (`custom1`), so a closure
  can let ticket holders through while keeping other traffic out. Emergency vehicles are always allowed.

## 3. How a diversion is simulated

- **Decision:** `set_diversion(junction, blocked_toward, send_to)` blocks the first 150 m or so of road
  leaving the junction towards `blocked_toward`. Drivers then pick their own way round. `send_to` is
  kept for the advisory text.
- **Why:** this matches how a police barricade works and needs no hand-drawn routes.

## 4. Two menu actions added: `open_road` and `remove_diversion`

- **Decision:** the agent can undo a closure or a diversion.
- **Why:** without them, the agent could only add restrictions, and the December 2024 case suggests some
  restrictions (for example closing the road to the ground at 11 AM) did more harm than good.

## 5. Every number is "compared with the normal evening"

- The normal evening is the same seed with the same normal trips and the same ambulance test trips,
  but no event and no plan. It runs once per scenario and is cached.
- **Total extra delay** = all time lost in traffic in the plan run minus all time lost in the normal run,
  in vehicle-hours. Visitors' own delay counts in full, because their trips don't exist without the event.
- **Ambulance check:** each test trip's travel time is compared with the same trip on the normal evening.
  The worst trip per hospital must stay within the limit (default 5 minutes); averaged over seeds.
- **Time to clear:** minutes after the show ends until extra delay on roads within 1.5 km of the venue
  stays under 10% of its post-show peak for 15 minutes.

## 6. Parking and overflow

- Visitors' cars fill lots first come, first served. Two-wheelers take a quarter of a car space.
- `assign_arrivals` sends a share of one direction's visitors to one lot; the rest go to the nearest open lot.
- If a lot is full, the car is sent to the nearest lot with space. If every lot is full, it parks
  informally near the venue, as happened in Sector 21 on 14 December 2024. The count is reported.
- Walking time = straight-line distance x 1.3 at 4 km/h. With a shuttle from that lot, it is ride time
  plus half the shuttle interval instead.

## 7. Named places are found automatically, then checked

- `data/places_spec.json` lists every place from the December 2024 advisories. The map build finds each
  one by its OpenStreetMap name first, then from the sector grid (sector centres are in OpenStreetMap,
  so a chowk where sectors 21, 22, 34 and 35 meet is near the middle of those four centres).
- Anything not found is printed for a hand fix in `data/places_manual.json`. Any plan step that uses a
  missing place is left out with a note, so the app never crashes on a missing name.
- Protected hospitals are taken from OpenStreetMap (amenity=hospital within 3 km of the venue), and the
  officer confirms them on step 2.

## 8. Simulations run as separate processes

- Each seed runs as `python -m sim.worker job.json`. This works the same on Windows and Linux and
  inside Streamlit, where Python's multiprocessing has problems.

## 9. Fixed-rule stand-in when Gemma is not running

- So the app never dead-ends during a demo, a simple rule set (shorten early closures, open a spare lot
  when lots overflow, remove a diversion at the worst junction, move one direction to the emptiest lot)
  stands in when Ollama is not reachable. It is labelled "Fixed rules (no AI)" everywhere.

## 10. Advisories: Gemma drafts, a template backs up

- The advisory is built from the plan's facts in fixed English, Hindi and Punjabi templates. Gemma
  rewrites them; the draft is rejected (and the template kept) if it drops a lot or road, or writes a
  number that is not in the plan.

## 11. Testing without the real map

- The build environment could not reach OpenStreetMap, so every part was tested on a stand-in grid
  (`scripts/make_test_grid.py`) and the map build was tested on a fake OSM file (deleted afterwards).
  The real Chandigarh map is built on the laptop. Results on the test grid mean nothing for the city.

## To record next (on the laptop)

- [ ] B3: the normal-traffic total chosen with `scripts/tune_normal.py`, and how it was checked.
- [ ] Any places fixed by hand in `places_manual.json`, and where the coordinates came from.
- [ ] Which Gemma model was used for the demo runs, and whether Colab was used.
- [ ] Sanity check: do Piccadilly Chowk, New Labour Chowk and the Sector 32 junction show up as trouble
      spots under Plan A? (docs/02, "How the demo uses this case", step 2)

## 12. Final check before Round 1 submission (16 Oct 2026)

- Re-ran the full app flow headless on the stand-in grid: load case, check, rehearse (3 rounds), compare, approve. No errors.
- Added the 6-slide pitch deck in `presentation/`.
- Laptop note: an i3-1220P with no GPU runs SUMO fine. Use Gemma 4 E2B on CPU (`ETR_MODEL=gemma4:e2b-it-qat`); expect 1 to 2 minutes per agent round.

## 13. Bug fixes before the next submission (28 Oct 2026)

Found by reading the code and the run logs from 22 and 23 October, then checked on the test grid.

- **Windows file lock.** After a run, deleting `routes.xml` could fail on Windows (`WinError 32`)
  because SUMO still held the file. The worker then crashed and the whole rehearsal stopped, even
  though the result was already saved (seen on 22 Oct, `normal_d8b43f52e3/seed11/worker.log`).
  `sim/runner.py` now skips a file it can't delete. The leftover XML file is harmless.
- **Time limit.** On the real map the normal evening plus round 1 took 113.5 minutes, so the
  30-minute limit stopped every rehearsal before Gemma could plan (23 Oct decision log). The limit
  is now 600 minutes, set in code as before, and can be changed with `ETR_MAX_MINUTES`. The app
  shows the real value on step 3.
- **Full map by default.** A fresh `scripts/build_network.py` run dropped residential roads, against
  the decision of 16 Oct. The full map is the default again; `--main-roads-only` is an option. The
  map already on the laptop was built before that change and is the full map, so nothing to rebuild.
- **Parking lots from the notice.** On 23 Oct Gemma E2B read the notice with no parking lots, so all
  visitors parked informally near the venue (22,400.7 vehicle-hours of extra delay, ambulance rule
  failed). `agent/extract.py` now adds any lot the keyword reader finds in the notice to Gemma's list.
  Only lots and the cab drop-off flag are merged: the keyword reader over-matches roads and diversions.
- **Not changed:** the 23 Oct evening run (Gemma E4B) stopped about 4 minutes in with an empty
  worker log. The same job ran past that point without a crash on Linux, so the simulation itself is
  not the cause. Likely the run was stopped from outside or the laptop ran short of memory with E4B
  loaded. If it happens again, use `set ETR_WORKERS=1` with E4B, or E2B, and don't click in the app
  while a rehearsal runs.
- **Tested** (test grid, SUMO 1.28.0): fixed-rule rehearsal and Gemma-path rehearsal end to end; a
  run with `routes.xml` locked finishes and keeps its result; a Gemma reply with no lots keeps all
  five lots from the real notice; `--main-roads-only` shows in `--help`. Still to run on the laptop:
  a real-map smoke test (`python scripts\check_setup.py`).
