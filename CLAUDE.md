# Instructions for Claude Code: find and fix the bugs in Event Traffic Rehearsal

Written on 28 October 2026 after a full review of this folder, the GitHub repo, the project docs and
the earlier chats. Read this whole file before you touch anything. Most of the diagnosis is already
done (sections 6 and 7), so do not spend time re-deriving it. Confirm, fix, test, report.

## 1. What this project is

A Streamlit app that lets a traffic officer rehearse an event's traffic plan before the day.

- Gemma 4 (local, through Ollama) is the planning agent. It reads the event notice, proposes changes
  to the traffic plan (closures, diversions, parking), reads the results and tries again.
- SUMO 1.28 (mesoscopic mode, run through libsumo) simulates each plan on the real Chandigarh road
  map, 1 PM to 1 AM, and compares it with the same evening without the event.
- Hard rules: ambulance trips to protected hospitals stay within 5 extra minutes, and no gridlock
  (more than 1% of vehicles teleported).
- The real case: the Diljit Dosanjh concert at the Exhibition Ground, Sector 34, 14 December 2024.

Five app steps: 1 Describe, 2 Check details, 3 Rehearse, 4 Compare plans, 5 Approve and publish.

## 2. People, machine and paths

- Author on every commit and document: **Parth Sarawagi** (git is already configured with this name).
- Repo: https://github.com/sarawagi716parth-del/event-traffic-rehearsal
- Branches: `main` is the exact Round 1 submission (tag `round1-submission`). **Never change `main`.**
  All work goes on `finale`. On 28 Oct this folder's code was identical to `origin/finale`.
- Folder: `C:\Users\Parth\Downloads\event-traffic-rehearsal\event-traffic-rehearsal`
- Laptop: Windows, Intel i3-1220P, no GPU, 16 GB RAM. Gemma runs on the CPU.
- Python: the worker logs show `C:\Users\Parth\AppData\Local\Programs\Python\Python311\python.exe`.
  There may also be a Python 3.14 on PATH that does not have the packages. Before running anything,
  check with `python -c "import libsumo, sumolib, streamlit; print('ok')"`. If that fails, use the
  full Python311 path above for every command.
- Shell: the user works in CMD. CMD syntax: `set ETR_NETWORK=testgrid`. PowerShell syntax:
  `$env:ETR_NETWORK="testgrid"`. Give him commands in the shell he is using.
- Not in git (gitignored, only on this laptop): `data/network/chandigarh/` (the real map: a 174 MB
  `city.net.xml`, `net_index.json`, `places_resolved.json`) and `runs/` (all simulation output).
  Do not delete or rebuild these.
- Useful environment variables: `ETR_NETWORK` (`chandigarh` or `testgrid`), `ETR_MODEL` (for example
  `gemma4:e2b-it-qat`), `ETR_WORKERS` (simulations at once), `OLLAMA_HOST`.

## 3. Rules for this job

1. **Minimal changes.** Fix bugs only. The code must still look like the GitHub repo: same structure,
   same style, same names. No refactors, no reformatting, no new dependencies, no new features.
2. Change only the lines a fix needs. If a fix seems to need more than about 20 lines, stop and ask Parth.
3. **Never reduce the road network by default.** Parth decided the full map stays the default for
   accuracy. A smaller map may only exist as an opt-in flag.
4. **Normal traffic stays at 30,000 trips a day.** That is the calibrated value (no stuck vehicles,
   main roads at 63% of the speed limit at 6 to 7 PM). Never change scenario assumptions to make
   results look better.
5. Never touch `main`. Work on `finale`. Do not push until Parth says yes.
6. After the fixes, add one entry to `docs/05-build-log.md` (format in section 10).
7. Talk to Parth in plain, simple English. Short sentences. No em dashes. Give exact commands he can
   copy, one step at a time, and say what he should see. Be direct and honest, including about
   anything you could not verify.

## 4. Read these first

| File | Why |
|---|---|
| `docs/05-build-log.md` | Every design decision so far (meso mode, closures, parking, metrics) |
| `docs/03-agent-design.md` | The agent loop, the menu, the guardrails and the budget |
| `docs/07-next-version-plan.md` | Planned work. Do not build any of it now |
| `sim/runner.py` | Runs one SUMO job; `run_many` starts worker processes |
| `sim/rehearsal.py` | Normal evening cache and plan runs on disk |
| `agent/loop.py` | The rehearsal loop and the `Budget` |
| `agent/extract.py` | Reads the event notice (Gemma or keywords) into a scenario and starting plan |
| `app/main.py` | The five screens |
| `scripts/build_network.py` | Builds the real map |

Context that is not in this folder (it lives in the claude.ai project): the finale plan said the
30-minute rehearsal limit had to be raised for the real map, Mohali needed an entry road, and eight
named places still need coordinates. Parth missed the 23 October finale. He now wants the project
working cleanly so he can submit it to another hackathon.

## 5. What happened on the laptop (evidence in `runs/diljit_dosanjh_concert_2024_12_14/`)

- `audit_log.jsonl`: rehearsals were started from "Read the notice" (Gemma), not from "Load this case".
- 22 Oct, normal evening with 120,000 trips (a wrong input, since fixed): the worker crashed with a
  Windows `PermissionError` (see bug 1). File: `normal_d8b43f52e3\seed11\worker.log`.
- 23 Oct morning, Gemma E2B, 1 repeat: the run took 113.5 minutes for one round, then stopped with
  "Reached the time limit (30 minutes)". Gemma never got to plan (bug 2). File: `decision_log.md`.
  The starting plan read from the notice had one closure and **no parking lots, no cab drop-offs and
  no diversions** (`r01\plan.json`), so about 4,900 visitor vehicles parked informally near the
  venue. Result: 22,400.7 vehicle-hours of extra delay and the ambulance rule failed (bug 4).
- 23 Oct evening, Gemma E4B: `r01\seed11` started at 19:45 and its files stopped changing at about
  19:49. `stats.xml` holds only the settings header (the run never finished) and `worker.log` is
  empty. Cause unknown (bug 5).
- Timings on this laptop: a normal evening (30,000 trips, full map) took about 10 minutes. Each
  simulation process uses about 3 GB of RAM.

## 6. Already checked on 28 October (do not repeat)

- On Linux with the same SUMO 1.28.0: the test grid runs end to end with the fixed-rule brain and
  with a stand-in Gemma server. All five app steps work in a browser: reading the notice, rounds,
  JSON retries (an invented number was rejected and retried), rejecting gridlocked plans, the
  what-if box, the plan summary and the three-language advisory.
- The exact job from the 23 Oct evening run (`r01\seed11\job.json`) was re-run on the real map on
  Linux. It ran 23 minutes and reached 18:10 simulated time with no crash, well past the point where
  the laptop run stopped. So that job does not crash SUMO by itself, at least on Linux.
- The keyword reader in `agent/extract.py` finds all five parking lots in
  `data/scenarios/diljit_notice.txt` and sees that cabs drop at the parking areas.

## 7. The bugs, in order

### Bug 1. Windows file lock kills a finished run

- **Symptom:** a simulation finishes, then the worker crashes, and the whole rehearsal stops with
  "Simulation failed".
- **Evidence:** `worker.log` above:
  `PermissionError: [WinError 32] The process cannot access the file because it is being used by
  another process: '...\routes.xml'` at `sim/runner.py`, line 175, `p.unlink(missing_ok=True)`.
- **Cause:** after `api.close()`, libsumo on Windows can still hold `routes.xml` open. Deleting an
  open file fails on Windows (it works on Linux, which is why earlier tests never saw it). The result
  file `raw.pkl.gz` is already saved at that point, so the run's work is lost for no reason.
- **Fix** in `sim/runner.py`, inside `run_one`, replace:

```python
    if not job.get("keep_xml"):
        for p in (routes, trip_out, edge_out):
            p.unlink(missing_ok=True)
```

with:

```python
    if not job.get("keep_xml"):
        for p in (routes, trip_out, edge_out):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                # Windows: SUMO can still hold a file for a moment after close(). The result
                # is already saved above, so a leftover XML file is harmless.
                pass
```

### Bug 2. The 30-minute limit stops Gemma after round 1 on the real map

- **Symptom:** "Stopped because: Reached the time limit (30 minutes)" after one round. Gemma never plans.
- **Cause:** `Budget.max_minutes = 30.0` in `agent/loop.py`. On the real map the normal evening plus
  round 1 already take longer than 30 minutes, so the loop stops before round 2. The finale plan
  asked for this limit to be raised.
- **Fix:**
  1. In `agent/loop.py`, add `import os` with the other imports, and change
     `max_minutes: float = 30.0` to
     `max_minutes: float = float(os.environ.get("ETR_MAX_MINUTES", 600))`.
     600 minutes (10 hours) fits 5 rounds with 1 repeat on this laptop. The limit is still enforced
     in code (guardrail 5), and `ETR_MAX_MINUTES` lets a faster server use a smaller value.
  2. In `app/main.py`, `step_rehearse()`, the text says `Limits: {S.rounds} rounds, 15 simulation
     runs, 30 minutes.` Replace the hard-coded `30 minutes` with `{Budget().max_minutes:.0f} minutes`
     (`Budget` is already imported there).

### Bug 3. A fresh map build drops residential roads, against Parth's decision

- **Symptom:** none yet on this laptop, because the current map was built before this code changed.
  But anyone who clones the repo and runs `scripts/build_network.py` (for example a hackathon judge)
  gets a smaller map with only main roads.
- **Cause:** on 16 October the main-roads-only setting was added, then Parth said to keep the full
  map. The revert (full map by default, `--main-roads-only` as an option) never reached this folder.
- **Fix** in `scripts/build_network.py` (keep `KEEP_TYPES` as it is):
  1. Delete these three lines from the `args` list in `netconvert()`:
     ```python
                 # Keep main and connecting roads only. Residential lanes multiply the network size
                 # several times and make every run slow on a laptop without changing which plan wins.
                 "--keep-edges.by-type", ",".join(f"highway.{t}" for t in KEEP_TYPES),
     ```
  2. Change `def netconvert():` to `def netconvert(main_roads_only=False):`, and right after the
     `args = [...]` list add:
     ```python
         if main_roads_only:  # optional: drop residential lanes for faster runs on small machines
             args += ["--keep-edges.by-type", ",".join(f"highway.{t}" for t in KEEP_TYPES)]
     ```
  3. In `main()`, after `ap.add_argument("--print-query", action="store_true")` add:
     ```python
         ap.add_argument("--main-roads-only", action="store_true", help="smaller, faster map without residential lanes")
     ```
     and change `netconvert()` to `netconvert(args.main_roads_only)`.
  4. Do **not** rebuild the map. This only changes what a fresh build does.

### Bug 4. Reading the notice with Gemma can drop every parking lot

- **Symptom:** the 23 Oct plan read from the notice had no parking, no cab drop-offs, no diversions.
  Every visitor parked informally, the run was very slow and the ambulance rule failed.
- **Cause:** the small model returned an empty or unmatched `parking_lots` list. `read_notice` trusts
  Gemma's lists completely. The keyword reader, which finds all five lots in the same notice, is only
  used when Gemma is not available.
- **Fix** (a guardrail in the same spirit as the others): in `agent/extract.py`, `read_notice()`,
  right after `source = "gemma"` add:

```python
            # Guardrail: a small model can leave out parking lots the notice names plainly.
            # Add any lot the keyword reader finds, so the starting plan never loses them.
            kw = keyword_fields(text)
            f.parking_lots = list(f.parking_lots) + [x for x in kw.parking_lots if x not in f.parking_lots]
            f.cabs_drop_at_parking = f.cabs_drop_at_parking or kw.cabs_drop_at_parking
```

  Merge only parking lots and the cab flag. Do **not** merge roads or diversions: the keyword reader
  over-matches those (it picks up Piccadilly Chowk as a diversion, though the notice only says to
  avoid it, and it matches four dividing roads where the notice closes one).
- **Also tell Parth:** for a demo, "Load this case" (the real police plan, Plan A) is the reliable
  path. "Read the notice" is the live Gemma moment.

### Bug 5. The 23 Oct evening run stopped about 4 minutes in (investigate, do not guess)

- The same job did not crash on Linux, and the empty `worker.log` means Python never raised an error.
  Likely causes, in order: the run was stopped from outside (window closed, Ctrl+C, laptop sleep), the
  laptop ran out of memory with Gemma E4B loaded on the CPU next to SUMO, or a Streamlit rerun (any
  click in the app while a rehearsal is running restarts the script and abandons the agent loop,
  while the SUMO processes carry on without it).
- Ask Parth what the screen showed when it stopped, and whether he clicked anything in the app while
  it ran.
- Reproduce it outside the app first: copy `r01\seed11\job.json` to a new folder, change `out_dir`
  in the copy to that folder, and run `python -m sim.worker <copied job.json>` from the project
  folder. Watch Task Manager memory. If it finishes, the simulation is fine and the cause was outside it.
- Change code for this only if you find the cause with evidence. If the cause is memory, the fix is
  a setting, not code: `set ETR_WORKERS=1` while Gemma E4B is loaded, or use E2B.

## 8. Known data gaps (not code bugs; leave them unless Parth asks)

From `data/network/chandigarh/places_resolved.json` and the build output:

- Eight named places have no position yet: New Labour Chowk, Gaushala Chowk, South End Chowk,
  Gurudwara Chowk, Sham Mall T-point, Polka turn, Yatri Niwas Chowk, Sector 14/15/24/25 Chowk.
  Because of this, `check_plan` leaves the Gaushala Chowk diversion out of Plan A, and the Sector
  14/25 and 24/25 dividing roads cannot be used. Parth fixes these by adding coordinates to
  `data/places_manual.json` and running `python scripts/build_network.py --skip-netconvert`.
- "Mohali: no entry roads found at the map edge" (its `fringe_bearing` is `[200, 300]`). The app
  drops Mohali's 20% of visitors and shares them out among the other origins. If Parth asks you to
  fix it, find out why `network.fringe_edges` returns nothing for that bearing before changing
  anything, and keep it a separate commit.

## 9. Slips visible to judges (ask Parth before changing)

- `README.md` still says `git clone https://github.com/<your-account>/event-traffic-rehearsal.git`.
  It should be `https://github.com/sarawagi716parth-del/event-traffic-rehearsal.git`.
- The finale plan also suggested a short README note that the code was written with an AI coding
  assistant.

## 10. How to test

Run each test from the project folder. Use the Python that has the packages (section 2).

**A. Quick check on the test grid (about 2 minutes), with the fixed-rule brain:**
```
set ETR_NETWORK=testgrid
python scripts\run_demo.py --brain rules --seeds 1 --rounds 3
```
You should see Round 1, then more rounds, then "Wrote ...docs\06-demo-results.md".
`docs\06-demo-results.md` from a test-grid run means nothing for the city: delete it, do not commit it.

**B. The same with Gemma (needs Ollama running):**
```
set ETR_MODEL=gemma4:e2b-it-qat
python scripts\run_demo.py --brain gemma --seeds 1 --rounds 3
```
Check that the first line says `Brain: Gemma (...)`, not "Fixed rules".

**C. The app on the test grid:** `streamlit run app\main.py` (with `ETR_NETWORK=testgrid` still
set). Step 3 should now show the new time limit. Click "Read the notice" with a short notice that
names "Test Lot North" and check step 2 lists it.

**D. Bug 4 without the app:**
```
set ETR_NETWORK=chandigarh
python -c "from agent.extract import keyword_fields; print(keyword_fields(open('data/scenarios/diljit_notice.txt').read()).parking_lots)"
```
It should print the five lots.

**E. Real map smoke test (long: 20 minutes to 2 hours; run it last, and do not click in other
windows that use a lot of memory while it runs):**
```
set ETR_NETWORK=chandigarh
set ETR_WORKERS=1
python scripts\check_setup.py
```
It ends with "Simulation works: normal evening + Plan A in ... s". The Gemma line may fail if Ollama
is not running; that is fine for this test.

## 11. When you are done

1. Add this entry to the end of `docs/05-build-log.md` (fill in what you actually did and saw):

```
## 13. Bug fixes before the next submission (28 Oct 2026)

- Windows file lock: deleting routes.xml after a run could fail on Windows and stop the whole
  rehearsal, even though the result was already saved. Leftover files are now skipped.
- Time limit: raised from 30 minutes to 600 (ETR_MAX_MINUTES). On the real map, round 1 alone took
  longer than 30 minutes, so Gemma never planned.
- Map build: the full map is the default again; --main-roads-only is optional, as decided on 16 Oct.
- Reading the notice: parking lots named in the notice are always kept, even if Gemma leaves them out.
- Tested: (list the tests from section 10 you ran and what they showed).
```

2. Show Parth `git status` and `git diff`, then list every changed file with one or two plain
   sentences: what changed and why.
3. Only after Parth says yes:
```
git add sim/runner.py agent/loop.py app/main.py scripts/build_network.py agent/extract.py docs/05-build-log.md
git commit -m "Fix Windows file lock after runs, raise rehearsal time limit, full map by default, keep notice parking lots"
git push origin finale
```
   Do not add `runs/`, `data/network/chandigarh/` or `docs/06-demo-results.md`. Ask Parth whether he
   wants this `CLAUDE.md` in the repo before adding it.
