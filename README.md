# Event Traffic Rehearsal

**Rehearse an event's traffic plan in a simulation before the day, not on the day.**

In December 2024 Chandigarh hosted two 20,000-person concerts at the Exhibition Ground in Sector 34. Both
jammed Piccadilly Chowk and New Labour Chowk, held up hospitals' access, and hit local traders. The
city moved the next show to Sector 25 after two difficult nights, and that show also caused trouble.
The fix was trial and error, on real roads, with real people stuck in it.

This tool lets a traffic officer try the plan first. Paste the event notice, and a local AI agent
(Gemma 4, running offline) rebuilds the plan, tests it in the SUMO traffic simulator on the Chandigarh
road network, finds the worst bottleneck, changes the plan, and tests again. The officer sees the
plans side by side on a map, asks "what if we close X?", and approves the final plan and a public
advisory in English, Hindi and Punjabi.

Built for **Code for Communities Chandigarh** (GDG Cloud Chandigarh), theme: *AI-Powered Traffic
Optimisation for Chandigarh*.

## What it does

1. **Describe**: paste the police notice. Gemma reads it into a scenario: venue, times, crowd, parking, closures.
2. **Check details**: the officer corrects anything wrong and sees every place on a map.
3. **Rehearse**: round 1 tests the officer's plan (in the demo, the real 14 Dec 2024 police plan).
   Each next round, Gemma names the worst bottleneck and makes up to 3 changes from a fixed menu.
   SUMO tests each plan 3 times with different random seeds against the same evening without the event.
4. **Compare plans**: total extra delay, delay for visitors and for everyone else, ambulance times to
   protected hospitals, time to clear after the show, closure hours in market areas, walking distance,
   and a map of roads coloured by extra wait (with the minutes written out, for colour-blind users).
5. **Approve and publish**: the advisory is drafted in three languages. Only the Approver role can approve.

### Hard rules the agent can never trade away
- Every ambulance test trip to a protected hospital stays within 5 extra minutes (officer can change).
- No gridlock (more than 1% of vehicles stuck long enough for SUMO to jump them forward rejects the plan).

### Guardrails that keep a small model reliable
1. Gemma must answer in a fixed JSON format (checked with Pydantic; up to 2 retries with the error).
2. Only menu actions and names from the places list; small misspellings are corrected, others rejected.
3. At most 3 changes per round, so it is clear what helped.
4. Every number Gemma writes is checked against the simulation results.
5. Round, run and time limits are enforced in code, not by the model.

### Privacy
Everything runs on one machine. Gemma runs through Ollama locally, so no event details or plans leave
the server. For a pilot, the same app runs on one government server (see `docs/00-platform-and-interface.md`).

## Run it on your laptop (Windows)

Do these in order. Each step says what you should see.

### 1. Install the tools (once)
1. **Python 3.12** from python.org. Tick **Add Python to PATH** during install.
2. **Git** from git-scm.com.
3. **Ollama** from ollama.com. Then, in a new PowerShell window:
   ```
   ollama pull gemma4:e4b-it-qat
   ollama pull gemma4:e2b-it-qat
   ollama show gemma4:e4b-it-qat
   ```
   The last command should list `tools` under capabilities. If a name is not found, check the exact
   names at https://ollama.com/library/gemma4 and use the same name in the app sidebar.

### 2. Get the code and the Python libraries
```
git clone https://github.com/sarawagi716parth-del/event-traffic-rehearsal.git
cd event-traffic-rehearsal
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
SUMO comes from pip (`eclipse-sumo`), so no separate installer is needed. If `libsumo` fails to
install, delete that line from `requirements.txt` and run the command again; the slower `traci`
is used automatically.

### 3. Build the Chandigarh map (once, needs internet, 2 to 5 minutes)
```
python scripts/build_network.py
```
It downloads roads and names from OpenStreetMap, builds the SUMO network, and places every named
chowk, light point, parking ground and hospital. It prints a list:
- `ok` lines: placed. "approximate" means it was placed from the sector grid; check it on the map.
- `MISSING` lines: not found by name. For each one, open Google Maps, right-click the spot, click
  the coordinates to copy them, and add a line to `data/places_manual.json`, for example
  `"Gaushala Chowk": [30.7012, 76.7654],`. Then run `python scripts/build_network.py --skip-netconvert`.

If the download fails, run `python scripts/build_network.py --print-query`, paste the printed query
into https://overpass-turbo.eu, export the result as raw OSM data, save it as
`data/network/chandigarh/chandigarh.osm.xml`, and run `python scripts/build_network.py --offline`.

### 4. Check everything
```
python scripts/check_setup.py
```
You should see `[ ok ]` on every line and one test run of Plan A with its timing.

### 5. Start the app
```
streamlit run app/main.py
```
It opens at http://localhost:8501. Click **Load this case**, then follow the five steps.
Switch the role in the sidebar to **Approver** to approve the plan.

### Optional: compute the demo in advance
```
python scripts/run_demo.py --seeds 3
```
This runs the Sector 34 rehearsal and the Sector 25 venue question, writes the decision log and
`docs/06-demo-results.md`. The app then shows the saved rehearsal on step 3. The same script runs
on Google Colab with a bigger Gemma model if the laptop model's plans are poor; say so in the demo.

### Testing without the real map
`python scripts/make_test_grid.py` builds a small stand-in grid (not Chandigarh). With
`set ETR_NETWORK=testgrid` the app and scripts use it. The app shows a warning whenever it is in use.

## How it is built

```
Officer's browser -> Streamlit app (app/) -> agent loop (agent/) <-> Gemma 4 via Ollama (local)
                                                 |
                                                 v
                           SUMO simulator, mesoscopic mode (sim/) <- Chandigarh network from OpenStreetMap
```

| Folder | What is in it |
|---|---|
| `sim/` | Scenario and plan formats, traffic generation, SUMO runs, metrics against the normal evening |
| `agent/` | The menu, Gemma prompts and checks, the rehearsal loop, plan summary and advisory |
| `app/` | The five screens and the styling |
| `data/` | Places list, the December 2024 scenario and police plans |
| `scripts/` | Build the map, check setup, tune normal traffic, run the demo |
| `docs/` | Planning documents, the build log and the decision log |
| `skills/` | An agent skill (Agent Skill format) for running a rehearsal |

## Honest limits

- The simulation is for **comparing plans fairly**, not predicting exact jam lengths. Normal traffic,
  crowd size, travel modes, parking capacities and signal timings are assumptions, listed in the app
  and in `docs/01-simulation-inputs.md`. A pilot would replace them with the city's own counts.
- Runs use SUMO's mesoscopic mode (queues per road) so a whole-city evening runs in minutes on a laptop.
- Positions found from the sector grid are approximate until checked.
- The fixed-rule stand-in (used only when Gemma is not running) is not AI, and the app says so.

## Credits and licences

- Code: Apache-2.0 (see `LICENSE`).
- Map data © OpenStreetMap contributors, Open Database License (ODbL).
- Simulator: Eclipse SUMO (Eclipse Public License 2.0), used as a separate program.
- Model: Gemma 4 (Apache 2.0), run locally through Ollama.
- Case facts: news reports listed in `docs/02-december-2024-concerts.md`. This is not an official
  Chandigarh Police or Government of India product.
