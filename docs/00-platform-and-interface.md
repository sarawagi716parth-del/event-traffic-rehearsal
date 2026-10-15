# Platform and interface decision

Status: decided on 16 October 2026. Revisit only if the hosting rules change.

## The decision in one line

A web app that runs on one secure server on government premises. Officers open it in an ordinary web browser on their office PCs, over the government network. For the hackathon, the same app runs on the laptop, which acts as both the server and the browser.

## The options we compared

| Option | Can it work? | Main problem | Verdict |
|---|---|---|---|
| Android app | Not for the core | SUMO only runs on Windows, Linux and macOS. Small Gemma models can run on phones, but the simulator can't. | Later, only as a companion view for officers in the field |
| Desktop software installed on each police PC | Partly | SUMO runs fine on an ordinary PC. Gemma is the problem: models good enough to plan need a graphics card with about 16 GB of memory or more, which office PCs don't have. Every PC would also need its own map, model and software updates, and plans would be scattered across PCs. | No |
| Public cloud (a private hosting company) | Yes | Ruled out by the security requirement: event plans and VIP routes shouldn't sit with a private company. | No |
| Web app on a government-hosted server | Yes | Needs one capable server and access to the government network | **Chosen** |

## Why the government-hosted web app wins

- **One powerful machine instead of many.** SUMO, Gemma and all the data live on one server with one good graphics card. Officers' PCs only need a browser.
- **Accessible where it matters.** Any police office on the government network can use it, and field officers can reach it over an approved VPN. It is not reachable from the open internet.
- **The AI runs fully offline.** Gemma's weights are open, so the AI runs on the server itself. No event details, VIP routes or plans are sent to Google or any other company. The only optional outside call is the weather lookup, which can be switched off.
- **One place to update.** Map changes, model upgrades and fixes happen once.
- **Shared history.** Every rehearsal, plan and approval is kept in one place, so the next event can learn from the last.
- **A natural home already exists.** Chandigarh's Integrated Command and Control Centre in Sector 17 already houses the Police Command and Control Centre. A government data centre, for example one run by NIC, is the other option.

## Security basics for a pilot

1. A login for every user, with three roles: Planner (creates rehearsals), Approver (approves plans and advisories) and Viewer (read only).
2. An audit log of who created, changed, approved or published what, and when.
3. No outside AI services. Gemma runs on the server.
4. The weather lookup can be turned off. The officer then enters rain by hand.
5. VIP movement scenarios are visible only to users with permission, and their public advisories list closures, never the route itself.
6. Regular backups of the project data.

## Server size for a pilot (estimates, to be confirmed by testing)

| Part | Suggested size | Why |
|---|---|---|
| Processor | 16 cores or more | Each simulation mostly uses one core, so the agent can test several plans at the same time |
| Memory | 64 GB | Several simulations plus the app running together |
| Graphics card | 24 GB or more | To run the larger Gemma 4 models (26B). A 16 GB card can run Gemma 4 12B. |
| Storage | 1 TB SSD | Simulation outputs add up quickly |
| Operating system | Ubuntu Linux (long-term support release) | SUMO, Ollama and Python all run well on it |

## Hackathon setup

| Machine | What runs there |
|---|---|
| Laptop (RTX 4050, 6 GB) | SUMO, the app and the agent loop. Gemma 4 E2B fits fully on the graphics card. Gemma 4 E4B also works, but Ollama splits it between graphics memory and system memory, so it is slower. |
| Google Colab, free tier (usually a T4 with 16 GB, when available) | Fallback if the small model's plans are poor: run the agent loop with Gemma 4 12B there, save the results, and show them in the app on the laptop. |

If the Colab fallback is used, say so in the demo: "These runs were computed in advance. In production, everything runs on the government server."

## Interface: look and feel

**Goal:** formal and calm, like DigiLocker. Not boxy and crowded like older government sites, and not flashy.

**Reference design system: UX4G.** UX4G (User Experience for Government) is the Government of India's design system, run by the National e-Governance Division (NeGD) under MeitY. Its published case studies include DigiLocker and UMANG, so following it gives exactly the DigiLocker feel, and it tells judges the tool is ready for government use.

- **Hackathon:** copy UX4G's look (colors, spacing, fonts, card style) using Streamlit's theme settings and a small CSS file.
- **Pilot:** rebuild the front end with UX4G's own web components.

**Rules**

1. Light background (white or very light grey) and one deep blue as the main color. Use green, amber and red only to show status.
2. Rounded cards with soft shadows for each event, plan and result, with plenty of white space. Avoid walls of tables.
3. One main action per screen, as a clear button in the same place every time, for example "Run rehearsal" or "Approve plan".
4. A step bar across the top: 1 Describe, 2 Check details, 3 Rehearse, 4 Compare plans, 5 Approve and publish.
5. Plain words, never simulation terms: "Road closures", not "edge restrictions". "Average extra wait", not "time loss".
6. A status chip on every item: Draft, Running, Ready for review, Approved.
7. On the results screen, the map is the centrepiece, with roads colored by delay. The legend also shows minutes as text, so the map works for color-blind users.
8. Fonts: Noto Sans for English, Noto Sans Devanagari for Hindi and Noto Sans Gurmukhi for Punjabi. One font family keeps all three languages consistent, and all are free on Google Fonts.
9. Works on common office screens (1366 × 768) and larger. Body text at least 16 px. Every action reachable by keyboard.
10. No emojis and no playful animations. Only short, subtle transitions.
11. Don't use the National Emblem of India, the Chandigarh Police logo or "Government of India" branding. Use of the emblem is restricted by the State Emblem of India (Prohibition of Improper Use) Act, 2005, and this project is not an official product. Use your own project name and a simple logo.

**Screens**

| # | Screen | What the officer does there | Stage |
|---|---|---|---|
| 1 | Home | Sees upcoming disruptions as cards (date, place, status) and starts a new rehearsal | Later |
| 2 | Describe | Pastes the event notice or fills a short form. Gemma fills in the details. | Must |
| 3 | Check details | Reviews the scenario card (venue, crowd, times, parking) and the assumptions, edits anything wrong, sees a map preview | Must |
| 4 | Rehearse | Watches each round run, with the agent's decision log appearing round by round | Must |
| 5 | Compare plans | Sees plans side by side: key numbers, a map for each plan, the recommended plan and the reasons. Can ask "What if we close X?" | Must |
| 6 | Approve and publish | Reviews the final plan and the advisory in English, Hindi and Punjabi, edits, approves (Approver role) and downloads | Must (simple version) |
| 7 | History | Past rehearsals with their plans and approvals | Later |

## What this decision means for the build

- Everything is written in Python.
- The app is a Streamlit web app, so it runs the same way on the laptop and on a server.
- Gemma runs through Ollama on the same machine.
- No database for the hackathon. Scenarios, plans, runs and logs are saved as files. A database comes with the pilot.

## Sources

- Police Command and Control Centre at the ICCC complex, Sector 17 (The Tribune): https://www.tribuneindia.com/news/chandigarh/union-home-secy-opens-police-command-control-centre-in-chandigarh-417378
- UX4G resources (NeGD, MeitY): https://www.ux4g.gov.in/resources
- UX4G 2.0 overview and case studies: https://ctrlfuture.substack.com/p/ux4g
- Gemma 4 models and sizes on Ollama: https://ollama.com/library/gemma4
