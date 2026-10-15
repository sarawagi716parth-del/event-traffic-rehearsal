# Simulation inputs: everything that goes into SUMO

## What this file is

A list of every value the simulator needs to rehearse a disruption: who sets it, where it comes from, and whether it is real data or our assumption.

One important point first: the simulation's job is to **compare plans fairly**, not to predict exact jam lengths. Values marked *Assumption* are our best guesses until a pilot gives us the city's own traffic counts. Keep them visible in the app so officers can see and change them.

## How to read the tables

- **Set by:** *System* (built once), *Gemma* (read from the event notice, then checked by the officer), *Officer* (a default the officer can change) or *Agent* (chosen while searching for the best plan).
- **Status:** *Real* (from a published source), *Estimate* (a real anchor plus our judgment) or *Assumption* (our guess until a pilot).
- **Stage:** *Must* (needed for tonight's submission), *If time*, or *Finals* (to build on 23 October if we reach the Top 20).

## A. The map

| # | Input | What it means | Set by | Source | Status | Stage |
|---|---|---|---|---|---|---|
| A1 | Simulated area | The part of the city we simulate | System | OpenStreetMap, through SUMO's OSM Web Wizard | Real | Must |
| A2 | Roads | Lanes, speed limits, one-way roads, turn rules | System | OpenStreetMap, converted by SUMO | Real, but check the main roads by eye | Must |
| A3 | Junction type | Roundabout (chowk), traffic light (light point) or simple junction | System | OpenStreetMap, plus SUMO's guess for traffic lights | Estimate | Must |
| A4 | Signal timings | How long each light stays green | System | Not public. Use SUMO's default fixed timings | Assumption | Must |
| A5 | Named places list | Chowks, light points, roads, parking lots, venue gates and hospitals, each linked to its spot on the SUMO map | System | OpenStreetMap names plus names used in police advisories, matched by hand once | Real | Must |

Notes:

- **A1:** Use all of Chandigarh's sectors. Traffic from Mohali, Panchkula and Zirakpur enters at the city's edge roads (see B6). If simulations run too slowly on the laptop, shrink the area to southern Chandigarh, but keep Sector 17 (parking), Sector 25 (Rally Ground), Sectors 29, 39, 43, 44 and 45 (parking used in December 2024) and the Gaushala Chowk and Faidan side (diversions).
- **A5:** Start with the names from the December 2024 advisories: Piccadilly Chowk, New Labour Chowk, the Sector 33/34 light point, Sham Mall T-point, Polka turn, Gaushala Chowk, South End Chowk, Gurudwara Chowk, Bhawan Vidyalaya School T-point, Sector 33/45 Chowk, Bhaskar Chowk, Sector 14/15/24/25 Chowk, Dadu Majra light point, Yatri Niwas Chowk, the Dhanas turn, and every parking ground listed in `02-december-2024-concerts.md`. The agent can only use names from this list.

## B. Normal traffic on that day

| # | Input | What it means | Set by | Source | Status | Stage |
|---|---|---|---|---|---|---|
| B1 | Day type | Weekday, Saturday, Sunday, public holiday or festival day | System | The event date plus an Indian holiday calendar (Python `holidays` library) | Real | Must |
| B2 | Hourly traffic curve | How busy each hour of the day is, for each day type | Officer (default) | No public counts exist for Chandigarh. Start with a standard two-peak curve: morning and evening rush | Assumption | Must |
| B3 | Total daily trips | The overall amount of normal traffic | Officer (default) | Tuned by hand (see the note below) | Assumption | Must |
| B4 | Vehicle mix | Shares of cars, two-wheelers, autos and buses | Officer (default) | Chandigarh's vehicle registrations by class (Vahan data) as a starting point. Registered vehicles aren't the same as vehicles on the road, so adjust | Estimate | If time |
| B5 | Where normal trips go | Which sectors trips start and end in | System | A random spread across the map for now. Later, weighted towards markets, offices and the industrial area | Assumption | Must (random), Finals (weighted) |
| B6 | Traffic from outside | Trips entering from Mohali, Panchkula, Zirakpur and the highways | Officer (default) | A share of total trips, added at the edge roads | Assumption | If time |
| B7 | City buses | CTU buses on their routes | System | CTU routes and timetables | Estimate | Finals |

**Note on B3:** tune this number until a normal Saturday evening without any event looks normal in the simulation: main roads busy, no gridlock. Record the value and how you checked it in the decision log.

## C. The disruption

One block per disruption. A day can have several blocks, for example a concert and a road repair. The agent plans for all of them together.

### C1. Fields for every disruption

| # | Input | What it means | Set by | Status | Stage |
|---|---|---|---|---|---|
| C1.1 | Type | Concert or match, festival market, road repair, rally or procession, VIP movement | Gemma, checked by the officer | Real | Must (concert), If time (road repair), Finals (the rest) |
| C1.2 | Location | The venue and its gates, a road stretch, or a route | Gemma, using the named places list | Real | Must |
| C1.3 | Date and times | Start and end time. For road repairs, the days and hours | Gemma, checked by the officer | Real | Must |
| C1.4 | Who may still pass closed roads | Emergency vehicles, buses, shuttles, ticket holders, residents with passes | Officer | Real (from advisories) | Must |

### C2. Extra fields for crowd events (concerts, matches, festival markets)

| # | Input | What it means | Set by | Source and demo value | Status | Stage |
|---|---|---|---|---|---|---|
| C2.1 | Expected crowd | Number of people | Gemma or officer | Ticket numbers from the organiser. Demo: Karan Aujla's 7 December 2024 show drew over 20,000 people. Diljit's crowd wasn't reported, so use 20,000, and also test 25,000 and 30,000 | Estimate | Must |
| C2.2 | Arrival spread | When people arrive | Officer (default) | Demo: arrivals from 3 PM until the show starts, busiest in the last two hours. For Diljit's show, venue entry opened at 3 PM. For Aujla's, diversions began at 2:30 PM | Estimate | Must |
| C2.3 | Exit surge | How fast people leave after the end | Officer (default) | Demo: most people leave within 45 minutes of the end | Assumption | Must |
| C2.4 | Travel mode split | Shares arriving by car, two-wheeler, cab or auto, and on foot | Officer (default) | Demo: car 50%, two-wheeler 25%, cab or auto 20%, walking or other 5% | Assumption | Must |
| C2.5 | People per vehicle | How many people share each vehicle | Officer (default) | Demo: car 2.5, two-wheeler 1.5, cab or auto 2.5 | Assumption | Must |
| C2.6 | Where visitors come from | Shares from each part of the Tricity and from outside | Officer (default) | Demo: Chandigarh 50%, Mohali 20%, Panchkula and Zirakpur 15%, outside the Tricity 15% | Assumption | Must |
| C2.7 | Parking areas | Each lot's location and capacity | Officer | Locations from police advisories. Capacity estimated from each ground's size on the map | Real (location), Estimate (capacity) | Must |
| C2.8 | Drop-off points | Where cabs and autos must drop people | Officer or agent | In December 2024, cabs had to drop people at the parking lots, not near the venue | Real | Must |
| C2.9 | Walking speed and shuttle time | Time from parking to the venue | System | Demo: walking at 4 km/h. Shuttle time comes from the simulation | Assumption | If time |

**Sanity check on the demo defaults:** 20,000 people works out to about 4,000 cars, 3,300 two-wheelers and 1,600 cab or auto trips. That's one parked car for every 5 visitors, close to the planned Sarangpur venue, which pairs about 35,000 people with 6,250 parking spaces (one car for every 5.6 people).

### C3. Extra fields for closures (road repairs, rallies, VIP movements)

| # | Input | What it means | Set by | Status | Stage |
|---|---|---|---|---|---|
| C3.1 | Road stretch | Which road, from which junction to which | Gemma, using the named places list | Real | If time |
| C3.2 | Lanes closed | All lanes or only some (repairs often close one side) | Gemma or officer | Real | If time |
| C3.3 | Closure window | From when to when. Repairs can last several days | Gemma or officer | Real | If time |
| C3.4 | Moving closure | For rallies and VIP convoys: the route, the speed, and how long each stretch stays blocked as it passes | Officer | Real (route), Assumption (timings) | Finals |
| C3.5 | Rally crowd | Number of marchers, gathering point and end point | Gemma or officer | Estimate | Finals |

## D. Conditions on the day

| # | Input | What it means | Set by | Source | Status | Stage |
|---|---|---|---|---|---|---|
| D1 | Rain | None, light or heavy | System, officer can override | Open-Meteo: forecast for future dates, past weather for replays such as 14 December 2024 | Real | If time |
| D2 | How rain changes driving | Slower speeds and bigger gaps between vehicles | System | Demo: light rain makes traffic 15% slower, heavy rain 30% slower | Assumption | If time |
| D3 | Other disruptions that day | More blocks from section C | Gemma or officer | Real | If time (two blocks), Finals (more) |
| D4 | Existing works and closures | Roads already closed that day for other reasons | Officer | Real | If time |

## E. Emergency access (a hard rule, never traded away)

| # | Input | What it means | Set by | Source | Status | Stage |
|---|---|---|---|---|---|---|
| E1 | Protected hospitals | Hospitals whose access must stay open | System, officer confirms | OpenStreetMap. In December 2024, four private hospitals and one medical college and hospital were reported near the Sector 34 ground | Real | Must |
| E2 | Ambulance test trips | Simulated ambulances from points around the venue to each protected hospital, every 15 minutes during the event | System | Our test design | Assumption | Must |
| E3 | Ambulance limit | The most extra travel time allowed | Officer | Demo: no more than 5 minutes longer than on a normal evening | Assumption (policy) | Must |

## F. The plan being tested

Chosen by the agent and tested in the simulator. The full menu is in `03-agent-design.md`.

| # | Input | Stage |
|---|---|---|
| F1 | Road closures: which roads, when, and who may still pass | Must |
| F2 | Diversions: at which junction, which direction is blocked, and where traffic goes instead | Must |
| F3 | Parking: which lots are open, and which arrival directions go to which lot | Must |
| F4 | Drop-off points for cabs and autos | Must |
| F5 | Shuttle buses: from which lot, how many, how often | If time |
| F6 | Staggered exit: which gates release people when | If time |
| F7 | Signal timing changes at light points | Finals |
| F8 | Event time shift (a suggestion only, because it needs the organiser's agreement) | Finals |

## G. Simulation settings

| # | Setting | Value and why | Stage |
|---|---|---|---|
| G1 | Time window | For an evening show, 1 PM to 1 AM. The first hours fill the roads with normal traffic before the event begins | Must |
| G2 | Time step | 1 second, SUMO's default | Must |
| G3 | Repeat runs | Run every plan 3 times with different random seeds and average the results, because small random differences change where jams form | Must |
| G4 | Stuck vehicles | SUMO normally jumps a vehicle forward if it has been stuck too long, which hides jams. Set the wait to 10 minutes, count every jump, and mark a plan as gridlocked if more than 1% of vehicles jump | Must |
| G5 | Two-wheeler behaviour | SUMO's sublane model lets two-wheelers squeeze between cars, which is closer to Indian traffic, but it makes runs slower | Finals |
| G6 | Outputs saved | Delay on every road every 5 minutes, every trip's travel time, ambulance trip times, queues at named junctions, and parking arrivals per lot | Must |

## H. What a pilot would replace

| Assumption today | Real data in a pilot | Source |
|---|---|---|
| Hourly traffic curve and total trips (B2, B3) | Hourly vehicle counts at junctions | The city's adaptive signal system and traffic cameras |
| Default signal timings (A4) | The real signal plans | The traffic police's signal system |
| Crowd size and travel mode split (C2.1, C2.4) | Tickets sold and parking passes issued | Event organisers |
| How rain changes driving (D2) | Counts and speeds from past rainy days | City traffic data |

After every real event, compare what the simulation showed with what actually happened (reported jams and counts), and adjust the defaults.

## Sources

- Karan Aujla concert crowd and parking, 7 December 2024 (The Tribune): https://www.tribuneindia.com/news/chandigarh/fans-groove-as-karan-aujla-casts-magic-spell-at-exhibition-ground/
- Diljit concert day: entry times and closures (The Tribune): https://www.tribuneindia.com/news/chandigarh/normal-life-business-hit-near-concert-venue/amp
- Diljit concert parking and diversions (PTC News): https://www.ptcnews.tv/nation/diljit-dosanjhamp039s-concert-in-chandigarh-today-elaborate-security-arrangements-in-place-at-sector-34-check-traffic-advisory-4403107
- Hospitals near Sector 34 (The Tribune): https://www.tribuneindia.com/news/chandigarh/no-more-big-ticket-concerts-at-sector-34-ground-admn/amp
- Planned Sarangpur venue, crowd and parking numbers (The Tribune): https://www.tribuneindia.com/news/chandigarh/soon-sarangpur-to-host-big-events/amp
- Chandigarh vehicle registrations by class (Dataful, from Vahan): https://dataful.in/datasets/18286
