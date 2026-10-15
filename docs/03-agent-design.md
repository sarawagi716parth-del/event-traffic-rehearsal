# The planning agent

## In one paragraph

Gemma 4 is the agent's brain, and SUMO is its test track. Given one or more disruptions, the agent proposes a traffic plan, tests it in the simulator, reads the results, finds the worst bottleneck, changes the plan and tests again. It stops when the plan stops improving, then recommends the best plan with its reasons and drafts the public advisory. It never controls real traffic and never publishes anything itself. An officer approves every plan.

## What the agent is trying to achieve

The agent follows these rules, in priority order:

1. **Ambulances get through (hard rule).** Every ambulance test trip to a protected hospital must stay within the limit. The default limit is no more than 5 minutes longer than on a normal evening. A plan that breaks this rule is rejected, however good its other numbers are.
2. **No gridlock (hard rule).** If more than 1% of vehicles get stuck long enough for SUMO to jump them forward, the plan is marked as gridlocked and rejected.
3. **Lowest total extra delay (main score).** This is the total extra time everyone spends on the road, compared with the same evening without the disruption, measured in vehicle-hours. It counts event visitors and everyone else.
4. **Tie-breakers, in order:** fewer hours of road closures inside residential and market areas (the Sector 34 traders' main complaint), a shorter time to clear the roads after the show, and shorter walks from parking.

The app shows all of these numbers separately to the officer, not just a single score.

## What the agent can see

| Input | What it contains | Where it comes from |
|---|---|---|
| Scenario | Every disruption that day, with crowd, times, parking and conditions | `01-simulation-inputs.md`, sections C and D, confirmed by the officer |
| Named places list | Every road, chowk, light point, parking lot (with capacity), venue gate and hospital the agent may use | System |
| Map summary | For each named place: which roads connect to it, and how far it is from the venue | System, generated from the SUMO map as text |
| Rules and budget | The hard rules, the scoring order and the run limits | System |
| Normal evening | The same day and time without the disruption, run once as the comparison | System |
| Starting plan | The officer's own plan, if there is one. In the demo, the real police plan from December 2024 | Officer |
| Results so far | The metrics from every run, and the decision log of every round | Simulator and agent |

### What each simulation run reports back

| Metric | Unit |
|---|---|
| Total extra delay | Vehicle-hours |
| Average extra delay for event visitors, and for everyone else | Minutes per trip |
| The five worst bottlenecks: place name, longest queue, longest wait, and when | Metres, minutes, time window |
| Ambulance time to each protected hospital: normal evening versus this plan, and pass or fail | Minutes |
| Parking: arrivals at each lot versus its capacity, and when each lot filled up | Vehicles, time |
| Time to clear: minutes after the show ends until roads near the venue are back to normal | Minutes |
| Road closure hours inside residential and market areas | Hours |
| Average walk from parking to the venue | Minutes |
| Stuck-vehicle jumps (the gridlock warning) | Count, and % of vehicles |

## The menu

Every action can only use names from the named places list. The system checks each action before it runs and sends an error back to the agent if anything is invalid. The example numbers below are illustrations, not real capacities.

### Look-up actions (read only)

| Action | What it does | Stage |
|---|---|---|
| `get_scenario()` | Returns the current scenario | Must |
| `list_places(kind)` | Lists named places of one kind: parking, junction, road, hospital or gate | Must |
| `describe_place(name)` | Gives a place's connections, its distance from the venue and, for lots, its capacity | Must |
| `get_results(run_id)` | Returns the full metrics of one run | Must |
| `compare_runs(run_ids)` | Returns a side-by-side table of several runs | Must |
| `get_weather(date, hour)` | Returns rain or no rain, from the cached Open-Meteo lookup | If time |

### Plan actions (each one changes the draft plan)

| Action | What it does | Example | Stage |
|---|---|---|---|
| `close_road(road, start, end, allow)` | Closes a road stretch for a time window. `allow` lists who may still pass: emergency vehicles, buses, shuttles, ticket holders or residents | Close the Sector 33/34 dividing road from 4 PM to 11 PM, allowing emergency vehicles and shuttles | Must |
| `set_diversion(junction, blocked_direction, send_to, start, end)` | Sends traffic from one approach onto another road | At Gaushala Chowk, send venue-bound traffic towards Faidan | Must |
| `open_parking(lot, limit)` and `close_parking(lot)` | Opens a lot with a vehicle limit, or closes it | Open the Sector 43 Dussehra Ground with a limit of 1,500 cars | Must |
| `assign_arrivals(origin, lot, share)` | Sends a share of visitors from one direction to one lot. Police already used this method for the Honey Singh show in March 2025 | Send all visitors from Mohali to Sector 43 | Must |
| `set_dropoff(point)` | Sets where cabs and autos must drop people | Sector 17 multilevel parking | Must |
| `block_turn(junction, from_road, to_road, start, end)` | Stops one turning movement at a junction | Stop right turns towards the venue at one chowk | If time |
| `close_lanes(road, lanes, start, end)` | Closes only some lanes, for road repairs | Close one lane of a road from 10 AM to 6 PM | If time |
| `add_shuttle(lot, buses, every_minutes, start, end)` | Runs shuttle buses between a lot and the venue | 12 buses, one every 5 minutes, from Sector 43 | If time |
| `stagger_exit(gate, minutes_after_end)` | Releases people from different gates at different times | Gate 2 opens 15 minutes after the end | If time |
| `adjust_signal(light_point, direction, extra_seconds)` | Gives more green time to one direction at a light point | 20 more seconds for the exit direction | Finals |
| `suggest_time_shift(minutes)` | Tests a different start time, marked "needs the organiser's agreement" | Start 30 minutes earlier | Finals |

### Testing actions

| Action | What it does | Stage |
|---|---|---|
| `run_simulation(plan, seeds=3)` | Runs the plan three times with different random seeds, and returns the averaged metrics and a run ID. Runs happen in parallel where the processor allows | Must |
| `run_normal_evening()` | Runs the same day without the disruption, once, as the comparison. The system does this before round 1 | Must |

### Output actions (drafts only)

| Action | What it does | Stage |
|---|---|---|
| `write_plan_summary(run_id)` | Writes a plain-language summary of the recommended plan and why it won, for the officer | Must |
| `draft_advisory(run_id, languages)` | Drafts the public advisory in English, Hindi and Punjabi: roads to avoid, where to park, and the timings | Must |
| `log_decision(...)` | Records each round: what changed, why, what the agent expected and what happened. The system calls this automatically every round | Must |

## Task access: what the agent may and may not do

**Allowed**

- Read the scenario, the named places list, the map summary, the run results and the cached weather.
- Build plans from the menu and test them in the simulator, within the budget.
- Write drafts of the plan summary and the advisory.

**Not allowed**

- Publishing or sending anything. Only an officer with the Approver role can approve and publish.
- Changing the map, the scenario facts (such as crowd size or times) or the hard rules. If the agent thinks a fact is wrong, it flags it for the officer instead.
- Using any place name that isn't in the named places list. The system rejects it.
- Using the internet (apart from the optional weather lookup, which can be switched off), personal data, or any live city system. The agent never touches real traffic lights. Everything happens inside the simulation.
- Going over budget: at most 5 rounds, 15 simulation runs and 30 minutes per rehearsal.

**Where a human decides**

1. **Before the rehearsal,** the officer checks and corrects the scenario Gemma built from the notice.
2. **During the rehearsal,** the officer can ask "What if we close X?" The agent tests the idea and reports the result honestly, even if it's worse.
3. **At the end,** an Approver approves the plan and the advisory. Nothing is published without that approval.
4. **Everything is recorded** in the audit log: every round, change, reason and approval.

## How one rehearsal runs

0. The system runs the normal evening once, as the comparison.
1. **Read.** Gemma turns the event notice into a scenario, and the officer checks it.
2. **Round 1.** Test the officer's own plan if there is one (in the demo, the real December 2024 police plan). Otherwise, Gemma proposes a first plan.
3. **Diagnose.** Gemma reads the results, names the worst bottleneck and explains why it happens.
4. **Improve.** Gemma makes one to three changes from the menu, each with a reason and the effect it expects.
5. **Test.** The simulator runs the new plan.
6. **Repeat** steps 3 to 5 until 5 rounds are done, or until the main score improves by less than 5% two rounds in a row.
7. **Report.** Present the best plan that passes both hard rules, a table of every round, the reasons, and the advisory drafts.

**Several disruptions on one day:** all of them go into one scenario and one plan. The bottleneck report says which disruption's traffic is causing each jam, so the agent can see when a fix for one event hurts another.

## Guardrails that keep a small model reliable

1. **A fixed answer format.** Every reply from Gemma must be JSON that matches a fixed schema, checked with Pydantic. If a reply fails the check, the error goes back to Gemma for up to 2 retries. After that, the round is skipped and logged.
2. **Menu only.** Place names are checked against the named places list. Small spelling differences, such as "Picadilly", are matched automatically with fuzzy matching. Anything else is rejected.
3. **Small steps.** At most 3 changes per round, so it's clear which change helped.
4. **No invented numbers.** The agent may only quote numbers that came from a simulation run, and its summary is checked against the run results.
5. **A hard stop.** The round and run limits are enforced by code, not by the model, which prevents endless loops.

## Decision log format

This example uses made-up numbers.

```
Round 2
Change:   Sent visitors from Mohali and Zirakpur to the Sector 43 Dussehra Ground
          instead of Sector 17.
Reason:   In round 1, Piccadilly Chowk had the longest queue (620 m), because
          traffic heading to Sector 17 parking crossed venue traffic there.
Expected: A shorter queue at Piccadilly Chowk, and more load near Sector 43.
Result:   Piccadilly Chowk queue down to 280 m. Gaushala Chowk queue up from
          150 m to 410 m. Total extra delay down 18%. Ambulance limit: passed.
Next:     Split the Sector 43 arrivals across two entry roads.
```

## Prompt skeleton for Gemma

Keep the real prompt this short. Long prompts slow small models down and make them less reliable.

```
You are a traffic planning assistant for a city police department.
Your job: find the traffic plan for the disruptions below that keeps the
total extra delay lowest, while following the hard rules.

Hard rules:
1. Ambulance trips to protected hospitals must stay within the limit.
2. Plans that cause gridlock are rejected.

Tie-breakers, in order: fewer closure hours in residential and market areas,
faster clearing after the show, shorter walks from parking.

Use only actions from the menu and place names from the places list.
Make at most 3 changes per round. Only quote numbers from the results you are given.

Scenario: {scenario_json}
Places: {places_list}
Menu: {menu_with_parameters}
Results so far: {results_table}

Reply only with JSON in this format:
{"diagnosis": "...",
 "changes": [{"action": "...", "args": {...}, "reason": "..."}],
 "expected_effect": "...",
 "stop": false}
```

## Hackathon scope

- **Must:** the look-up actions, `close_road`, `set_diversion`, the parking actions, `assign_arrivals`, `set_dropoff`, `run_simulation`, `run_normal_evening`, both output actions, the decision log and all five guardrails.
- **If time:** `block_turn`, `close_lanes` (for road repairs), `add_shuttle`, `stagger_exit` and `get_weather`.
- **Finals:** `adjust_signal`, `suggest_time_shift`, and moving closures for rallies and VIP convoys.

## Sources

- Police assigned parking by direction of arrival for the Honey Singh show (The Tribune): https://www.tribuneindia.com/news/chandigarh/admn-all-geared-up-for-honey-singh-show-today
- Traders' complaints about the Sector 34 closures (The Tribune): https://www.tribuneindia.com/news/chandigarh/no-more-big-ticket-concerts-at-sector-34-ground-admn/amp
