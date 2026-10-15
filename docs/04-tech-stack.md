# Tech stack

## The whole system in one picture

```
Officer's web browser
        |
        v
Streamlit app (Python) ----saves----> project files: scenarios, plans, runs, decision logs
        |
        v
Agent loop (Python) <------------> Gemma 4, running locally through Ollama
        |
        v
SUMO traffic simulator, controlled from Python <---- Chandigarh road network built from OpenStreetMap
```

On the laptop, all of this runs on one machine. In a pilot, it all moves to one government server unchanged (see `00-platform-and-interface.md`).

## Models

| Model | Ollama name | Download size | Job | Where it runs |
|---|---|---|---|---|
| Gemma 4 E2B | `gemma4:e2b-it-qat` | 4.3 GB | Agent brain during development | Laptop. Fits on the RTX 4050's 6 GB |
| Gemma 4 E4B | `gemma4:e4b-it-qat` | 6.1 GB | A better agent brain | Laptop. Slightly larger than the graphics card, so Ollama puts part of it in system memory, which makes it slower |
| Gemma 4 12B | `gemma4:12b-it-qat` | 7.2 GB | Agent brain for the final demo runs | Google Colab's free GPU (16 GB), if the E4B model's plans are poor |
| Gemma 4 26B | `gemma4:26b-a4b-it-qat` | 16 GB | Agent brain in a pilot | Government server with a 24 GB or larger graphics card |
| TranslateGemma (optional) | Check the current name | Varies | Hindi and Punjabi advisories, only if Gemma 4's own translations aren't good enough | Laptop or server. Confirm it supports Punjabi first |

- All Gemma 4 models have open weights under the Apache 2.0 license, and Ollama's page lists native function calling for them.
- **No training or fine-tuning is needed.** The models are used as they are, so training costs nothing.
- Model names on Ollama can change. Before pulling, confirm the exact names on Ollama's Gemma 4 page, then pull with, for example: `ollama pull gemma4:e4b-it-qat`
- Before relying on tool calling, check the model with `ollama show gemma4:e4b-it-qat`. "tools" should appear under its capabilities.

## Software

| Software | Why | How to get it |
|---|---|---|
| Python 3.12 | The language for everything | python.org. On Windows, tick "Add Python to PATH" during installation |
| Eclipse SUMO (latest release) | The traffic simulator, plus its tools: OSM Web Wizard, netconvert, randomTrips, duarouter and sumo-gui | The Windows installer from the SUMO website, or `pip install eclipse-sumo`. Afterwards, the `SUMO_HOME` environment variable must point to the SUMO folder. The Windows installer sets this for you |
| Ollama | Runs Gemma on your own machine and gives Python a local connection to it | The installer from ollama.com |
| Git and a GitHub account | Version control, and the public repository the submission needs | git-scm.com and github.com |
| VS Code | Code editor | code.visualstudio.com |
| Google Colab | Free GPU fallback for the bigger Gemma model | colab.research.google.com |
| OBS Studio | Free screen recorder for the demo video | obsproject.com |
| Chrome or Edge | To use the app | Already installed |

## Languages

| Language | Used for |
|---|---|
| Python | Everything: building traffic, running SUMO, the agent and the app |
| XML | SUMO's own files (network, routes, settings). Python code generates them, so you rarely write XML by hand |
| JSON | Scenarios, plans, results and Gemma's answers |
| CSS | One small file to style the app |
| Markdown | The docs and the README |

## Frameworks

| Framework | Used for | Notes |
|---|---|---|
| Streamlit | The app | A Python framework for web apps. It runs as a small web server, so the same app works on the laptop and on a server |
| Plain Python agent loop | The agent | Recommended first: Gemma answers in JSON, and Python runs the chosen action. Simple and easy to debug |
| Google ADK (optional) | The agent, as an alternative | Google's open-source Agent Development Kit. It runs Gemma through Ollama using LiteLLM. Use the model prefix `ollama_chat/`, not `ollama/`: ADK's docs warn that the plain prefix can cause endless tool-call loops. The Women in Tech Punjab edition of Code for Communities gave extra credit for using ADK |
| FastAPI and UX4G web components | A sturdier version of the app for a pilot | Not for tonight |

## Python libraries

| Library | Job |
|---|---|
| `traci` | Controls a running SUMO simulation from Python, for example closing roads or reading queues |
| `libsumo` | Does the same job as `traci` but faster, without the visual window. Use it for the agent's many test runs. If it won't install on Windows, use `traci`; it's slower but works the same way |
| `sumolib` | Reads the road network, converts map positions to latitude and longitude, and reads SUMO's output files |
| `ollama` | Talks to Gemma from Python |
| `pydantic` | Checks that Gemma's JSON matches the plan format |
| `pandas` | Results tables |
| `streamlit` | The app |
| `folium` and `streamlit-folium` | The map, with roads colored by delay |
| `plotly` | Charts, for example delay over time |
| `rapidfuzz` | Matches place names despite spelling differences |
| `requests` | The weather lookup from Open-Meteo |
| `holidays` | Indian public holidays, for the day type |
| `google-adk` and `litellm` | Only if you use ADK |

Already built into Python, nothing to install: `concurrent.futures` (to run several simulations at once), `json`, `subprocess` and `pathlib`.

**Install command:**

```
pip install traci libsumo sumolib ollama pydantic pandas streamlit folium streamlit-folium plotly rapidfuzz requests holidays
```

If you installed SUMO with pip, add `eclipse-sumo` to the same line. Keep `eclipse-sumo`, `traci`, `libsumo` and `sumolib` on the same version number, because mismatched versions cause errors.

## Data sources

| Data | Used for | Terms |
|---|---|---|
| OpenStreetMap | The road network and place names | Open Database License (ODbL). Credit "© OpenStreetMap contributors" in the README and in the app. The SUMO network built from it stays under the ODbL |
| Open-Meteo | Rain forecasts, and past weather for replays such as 14 December 2024 | Free for non-commercial use, no key needed. Credit Open-Meteo |
| Police advisories and news reports | The December 2024 case, and the parking and closure details | Keep facts and links in the repo, not copied article text |
| Chandigarh vehicle registrations by class (Vahan data, via Dataful) | A starting point for the vehicle mix | Optional |

## Hardware

- **Hackathon:** the laptop (RTX 4050, 6 GB), with Google Colab's free GPU as a fallback.
- **Pilot:** one government server. See `00-platform-and-interface.md` for the sizing.

## Repository layout

```
event-traffic-rehearsal/
├── README.md              what it is, how to run it, screenshots, credits
├── LICENSE                Apache-2.0
├── requirements.txt       the Python libraries above
├── docs/                  these planning files and the decision log
├── data/
│   ├── network/           Chandigarh road network built from OpenStreetMap
│   ├── places.json        the named places list
│   └── scenarios/         one file per event, e.g. diljit_2024-12-14.json
├── sim/                   build traffic, run SUMO, read results
├── agent/                 the agent loop, menu actions, prompts, JSON schemas
├── app/                   Streamlit screens, theme and CSS
├── scripts/               build the network, run the demo, export results
└── runs/                  simulation outputs (not committed to Git)
```

## Licenses

- **Your code:** Apache-2.0, the same license as Gemma 4. The bonus challenge needs a public GitHub repo with an open-source license.
- **SUMO:** Eclipse Public License 2.0. Use it as a separate program, and don't copy its source code into your repo.
- **Map data:** ODbL, with credit to OpenStreetMap contributors.
- **Gemma 4:** Apache 2.0.

## Sources

- Gemma 4 models on Ollama: https://ollama.com/library/gemma4
- Gemma 4 Ollama names and download sizes: https://leetllm.com/blog/run-gemma4-local-ollama
- Gemma 4 release and Apache 2.0 license: https://letsdatascience.com/news/google-releases-gemma-4-open-models-05c4c02a
- Gemma releases, including TranslateGemma: https://ai.google.dev/gemma/docs/releases
- Using Ollama models in Google ADK: https://adk.dev/agents/models/ollama/
- Code for Communities: Women in Tech Punjab (ADK credit): https://gdg.community.dev/events/details/google-gdg-jalandhar-presents-code-for-communities-women-in-tech-punjab/cohost-gdg-jalandhar/
- UX4G resources: https://www.ux4g.gov.in/resources
