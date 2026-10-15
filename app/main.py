"""Event Traffic Rehearsal: the officer's app.

    streamlit run app/main.py

Five steps: Describe, Check details, Rehearse, Compare plans, Approve and publish.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Pick the map before anything loads it: the real Chandigarh map if it has been built,
# otherwise the stand-in test grid (clearly labelled).
if "ETR_NETWORK" not in os.environ:
    os.environ["ETR_NETWORK"] = ("chandigarh" if (ROOT / "data/network/chandigarh/places_resolved.json").exists()
                                 else "testgrid")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from streamlit_folium import st_folium  # noqa: E402

from agent import extract, report  # noqa: E402
from agent.brain import DEFAULT_MODEL, OllamaBrain, RuleBrain  # noqa: E402
from agent.loop import Agent, Budget, what_if  # noqa: E402
from agent.menu import MENU_TEXT, check_plan, fill_scenario_defaults  # noqa: E402
from agent.schemas import RoundReply  # noqa: E402
from app import maps  # noqa: E402
from sim import config, metrics, places  # noqa: E402
from sim.models import Plan, Scenario  # noqa: E402
from sim.rehearsal import Rehearsal  # noqa: E402

APP_NAME = "Event Traffic Rehearsal"
STEPS = ["Describe", "Check details", "Rehearse", "Compare plans", "Approve and publish"]
NET = config.NETWORK_NAME
TEST_MAP = NET == "testgrid"

st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="expanded")
st.markdown(f"<style>{(ROOT / 'app/theme.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

S = st.session_state
S.setdefault("step", 0)
S.setdefault("role", "Planner")


# ---------------------------------------------------------------- helpers
def audit(R: Rehearsal | None, action: str, detail: str = ""):
    if R is None:
        return
    rec = {"time": dt.datetime.now().isoformat(timespec="seconds"), "user_role": S.role, "action": action,
           "detail": detail}
    with open(R.dir / "audit_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def chip(text, kind):
    return f'<span class="chip {kind}">{text}</span>'


def card(html, best=False):
    st.markdown(f'<div class="etr-card{" best" if best else ""}">{html}</div>', unsafe_allow_html=True)


def get_brain():
    if S.get("brain_choice", "gemma") == "gemma":
        ok, msg = OllamaBrain.available(S.get("model", DEFAULT_MODEL))
        if ok:
            return OllamaBrain(S.get("model", DEFAULT_MODEL))
    return RuleBrain()


def default_files():
    if TEST_MAP:
        d = config.network_dir("testgrid")
        return d / "scenario.json", d / "plan_police.json"
    return ROOT / "data/scenarios/diljit_2024-12-14.json", ROOT / "data/plans/police_2024-12-14_sector34.json"


def rehearsal() -> Rehearsal | None:
    if "scenario" not in S:
        return None
    return Rehearsal(S.scenario, seeds=config.DEFAULT_SEEDS[: S.get("seeds", 3)])


def goto(i):
    S.step = i
    st.rerun()


# ---------------------------------------------------------------- header, sidebar, step bar
st.markdown(f"""<div class="etr-header"><div class="etr-logo">ER</div><div>
<div class="etr-title">{APP_NAME}</div>
<div class="etr-sub">Rehearse an event's traffic plan in a simulation before the day. Every plan is a draft until an approver signs it off.</div>
</div></div>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("**Signed in as**")
    S.role = st.selectbox("Role", ["Planner", "Approver", "Viewer"], index=["Planner", "Approver", "Viewer"].index(S.role),
                          help="Pilot version: real logins come later. Only an Approver can approve and publish.")
    st.divider()
    st.markdown("**Planning assistant**")
    S.brain_choice = st.radio("Brain", ["gemma", "rules"], format_func=lambda x: {"gemma": "Gemma 4 (local, Ollama)",
                              "rules": "Fixed rules (no AI)"}[x], index=0 if S.get("brain_choice", "gemma") == "gemma" else 1)
    S.model = st.text_input("Gemma model", S.get("model", DEFAULT_MODEL))
    if S.brain_choice == "gemma":
        ok, msg = OllamaBrain.available(S.model)
        st.markdown(chip("Ready", "pass") if ok else chip("Not available", "fail"), unsafe_allow_html=True)
        st.caption(msg if not ok else "Runs on this machine. Nothing is sent outside.")
        if not ok:
            st.caption("The fixed-rule stand-in will be used until Gemma is running.")
    st.divider()
    st.markdown("**Simulation**")
    S.seeds = st.slider("Repeat runs per plan", 1, 3, S.get("seeds", 3),
                        help="Each plan runs this many times with different random seeds; results are averaged.")
    S.rounds = st.slider("Most rounds", 2, 5, S.get("rounds", 5))
    st.caption(f"Map: {'stand-in TEST GRID (not Chandigarh)' if TEST_MAP else 'Chandigarh (OpenStreetMap)'}")
    st.caption("Map data © OpenStreetMap contributors (ODbL). Simulation: Eclipse SUMO.")

if TEST_MAP:
    st.warning("Running on the stand-in test grid, not the Chandigarh map. Build the real map with "
               "`python scripts/build_network.py` and restart the app.")

bar = []
for i, name in enumerate(STEPS):
    cls = "active" if i == S.step else ("done" if i < S.step else "")
    bar.append(f'<div class="etr-step {cls}"><b>{i + 1}</b>{name}</div>')
st.markdown(f'<div class="etr-steps">{"".join(bar)}</div>', unsafe_allow_html=True)
nav = st.columns(len(STEPS))
for i, name in enumerate(STEPS):
    reachable = i == 0 or ("scenario" in S and (i <= 2 or S.get("agent_out")))
    if nav[i].button(f"Go to {i + 1}", key=f"nav{i}", disabled=not reachable or i == S.step,
                     width="stretch"):
        goto(i)


# ---------------------------------------------------------------- 1. Describe
def step_describe():
    st.subheader("1. Describe the event")
    st.markdown('<p class="etr-muted">Paste the event notice, or load the December 2024 case. '
                'Gemma reads the notice and fills in the details for you to check on the next screen.</p>',
                unsafe_allow_html=True)
    scn_file, plan_file = default_files()
    left, right = st.columns([3, 2])
    with left:
        sample = (ROOT / "data/scenarios/diljit_notice.txt")
        default_text = sample.read_text(encoding="utf-8") if sample.exists() and not TEST_MAP else ""
        text = st.text_area("Event notice", S.get("notice", default_text), height=260)
        if st.button("Read the notice", type="primary", disabled=S.role == "Viewer" or not text.strip()):
            S.notice = text
            brain = get_brain()
            with st.spinner("Reading the notice" + (" with Gemma" if brain.kind == "gemma" else "")):
                fields, source, problems = extract.read_notice(text, brain)
                template = Scenario.model_validate_json(scn_file.read_text(encoding="utf-8"))
                scn, plan = extract.to_scenario_and_plan(fields, template)
            set_scenario(scn, plan, f"Read by {'Gemma' if source == 'gemma' else 'keyword matching (Gemma not running)'}",
                         problems)
            goto(1)
    with right:
        card("<h4>December 2024 case</h4><p class='etr-muted'>Diljit Dosanjh concert, Exhibition Ground, "
             "Sector 34, 14 Dec 2024, with the police plan published for that day as Plan A.</p>"
             if not TEST_MAP else "<h4>Test case</h4><p class='etr-muted'>A test concert on the stand-in grid.</p>")
        if st.button("Load this case", disabled=S.role == "Viewer"):
            scn = Scenario.model_validate_json(scn_file.read_text(encoding="utf-8"))
            plan = Plan.model_validate_json(plan_file.read_text(encoding="utf-8"))
            set_scenario(scn, plan, "Loaded from saved files", [])
            goto(1)
        if not TEST_MAP and (ROOT / "data/scenarios/diljit_at_sector25.json").exists():
            card("<h4>Venue question</h4><p class='etr-muted'>The same crowd at the Rally Ground, Sector 25, "
                 "with the plan police used for AP Dhillon on 21 Dec 2024.</p>")
            if st.button("Load the Sector 25 case", disabled=S.role == "Viewer"):
                scn = Scenario.model_validate_json((ROOT / "data/scenarios/diljit_at_sector25.json").read_text())
                plan = Plan.model_validate_json((ROOT / "data/plans/police_2024-12-21_sector25.json").read_text())
                set_scenario(scn, plan, "Loaded from saved files", [])
                goto(1)


def set_scenario(scn: Scenario, plan: Plan, source: str, problems: list[str]):
    scn, notes = fill_scenario_defaults(scn)
    plan, warns = check_plan(plan)
    S.scenario, S.start_plan = scn, plan
    S.source, S.problems = source, problems + notes + warns
    for k in ("agent_out", "summary", "advisory", "approved", "whatif"):
        S.pop(k, None)
    R = rehearsal()
    audit(R, "scenario created", source)


# ---------------------------------------------------------------- 2. Check details
def step_check():
    st.subheader("2. Check the details")
    scn: Scenario = S.scenario
    ev = scn.events[0]
    st.markdown(chip("Draft", "draft") + f'<span class="etr-muted">{S.source}</span>', unsafe_allow_html=True)
    for p in S.get("problems", []):
        st.info(p)
    locked = S.role == "Viewer"
    a, b = st.columns([3, 2])
    with a:
        with st.form("scenario_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Event", ev.name, disabled=locked)
            venues = places.names("venue")
            venue = c2.selectbox("Venue", venues, index=venues.index(ev.venue) if ev.venue in venues else 0,
                                 disabled=locked)
            c1, c2, c3, c4 = st.columns(4)
            date = c1.text_input("Date (YYYY-MM-DD)", ev.date, disabled=locked)
            arr = c2.text_input("Arrivals from", ev.arrival_start, disabled=locked)
            start = c3.text_input("Show starts", ev.show_start, disabled=locked)
            end = c4.text_input("Show ends", ev.show_end, disabled=locked)
            c1, c2, c3 = st.columns(3)
            crowd = c1.number_input("Expected crowd", 1000, 100000, ev.crowd, step=1000, disabled=locked)
            exit_m = c2.number_input("Most people leave within (min)", 10, 180, ev.exit_minutes, disabled=locked)
            rain = c3.selectbox("Rain", ["none", "light", "heavy"], index=["none", "light", "heavy"].index(scn.rain),
                                disabled=locked)
            st.markdown("**How visitors travel** (shares of people)")
            c = st.columns(4)
            ms = {k: c[i].number_input(k.replace("_", " "), 0.0, 1.0, float(ev.mode_split.get(k, 0)), 0.05,
                                       disabled=locked) for i, k in enumerate(["car", "two_wheeler", "cab", "walk"])}
            st.markdown("**Where visitors come from** (shares)")
            origins = list(ev.origin_shares)
            c = st.columns(max(len(origins), 1))
            os_ = {k: c[i].number_input(k, 0.0, 1.0, float(ev.origin_shares[k]), 0.05, disabled=locked)
                   for i, k in enumerate(origins)}
            hosp_all = places.names("hospital")
            hosp = st.multiselect("Protected hospitals (ambulance access must stay open)", hosp_all,
                                  [h for h in scn.protected_hospitals if h in hosp_all], disabled=locked)
            c1, c2 = st.columns(2)
            amb = c1.number_input("Ambulance limit: most extra minutes allowed", 1.0, 30.0,
                                  float(scn.ambulance_limit_min), 0.5, disabled=locked)
            trips = c2.number_input("Normal traffic: trips per day (tuned by hand)", 5000, 2000000,
                                    scn.normal.total_daily_trips, 5000, disabled=locked)
            saved = st.form_submit_button("Save changes", disabled=locked)
        if saved:
            try:
                ev2 = ev.model_copy(update={"name": name, "venue": venue, "date": date, "arrival_start": arr,
                                            "show_start": start, "show_end": end, "crowd": int(crowd),
                                            "exit_minutes": int(exit_m), "mode_split": ms, "origin_shares": os_})
                scn2 = scn.model_copy(update={"events": [ev2], "rain": rain, "protected_hospitals": hosp,
                                              "ambulance_limit_min": amb,
                                              "normal": scn.normal.model_copy(update={"total_daily_trips": int(trips)})})
                S.scenario = Scenario.model_validate(scn2.model_dump())
                audit(rehearsal(), "scenario edited")
                st.success("Saved.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not save: {exc}")
        veh = S.scenario.events[0].vehicles()
        card(f"<h4>What this means on the road</h4><p class='etr-muted'>About {veh['car']:,} cars, "
             f"{veh['two_wheeler']:,} two-wheelers and {veh['cab']:,} cab or auto trips for the event. "
             f"Day type: {S.scenario.day_type()}.</p>")
        with st.expander("Assumptions (shown so they can be checked and changed)"):
            for x in S.scenario.assumptions or ["Defaults from docs/01-simulation-inputs.md"]:
                st.markdown(f"- {x}")
    with b:
        st.markdown("**Starting plan**")
        plan: Plan = S.start_plan
        card(f"<h4>{plan.name}</h4>" + "".join(f"<div class='etr-muted'>• {x}</div>" for x in plan.plain_lines()))
        st.markdown("**Map preview**")
        m = maps.preview_map(S.scenario.events[0].venue, plan.open_lots(), S.scenario.protected_hospitals, plan)
        st_folium(m, height=380, use_container_width=True, returned_objects=[])
        st.caption("Blue star: venue. Green: parking used. Grey: other lots. Red: protected hospitals. "
                   "Dashed blue: closed roads. Hover for names and how each position was found.")
    if st.button("Details are correct: go to rehearsal", type="primary", disabled=locked):
        audit(rehearsal(), "scenario confirmed")
        goto(2)


# ---------------------------------------------------------------- 3. Rehearse
def render_round(r: dict):
    head = f"Round {r['round']}" + (f" · {r['plan_name']}" if r.get("plan_name") else "")
    lines = []
    if r.get("skipped"):
        lines.append(f"Skipped:  {r['result']}")
    else:
        lines.append("Change:   " + "; ".join(r.get("changes", [])))
        if r.get("reasons"):
            lines.append("Reason:   " + " ".join(x for x in r["reasons"] if x))
        if r.get("diagnosis"):
            lines.append("Diagnosis: " + r["diagnosis"])
        if r.get("expected"):
            lines.append("Expected: " + r["expected"])
        lines.append("Result:   " + r.get("result", ""))
        if r.get("rejected"):
            lines.append("Rejected by the menu check: " + " | ".join(r["rejected"]))
    card(f"<h4>{head}</h4><div class='etr-log'>{'<br>'.join(_esc(x) for x in lines)}</div>")


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def step_rehearse():
    st.subheader("3. Rehearse")
    R = rehearsal()
    log_file = R.dir / "decision_log.json"
    brain = get_brain()
    st.markdown(f'<p class="etr-muted">Round 1 tests the starting plan. Then the planning assistant '
                f'({brain.label}) finds the worst bottleneck, changes up to 3 things, and tests again. '
                f'Limits: {S.rounds} rounds, 15 simulation runs, 30 minutes.</p>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 3])
    run = c1.button("Run rehearsal", type="primary", disabled=S.role != "Planner" and S.role != "Approver")
    if log_file.exists() and not run:
        c2.caption("Showing the last rehearsal saved for this event. Run again to start fresh.")
    status = st.empty()
    feed = st.container()
    if run:
        for old in R.dir.glob("r[0-9][0-9]"):
            import shutil
            shutil.rmtree(old, ignore_errors=True)
        log_file.unlink(missing_ok=True)
        audit(R, "rehearsal started", brain.label)

        def on_event(e):
            if e["type"] == "status":
                status.markdown(chip("Running", "running") + _esc(e["text"]), unsafe_allow_html=True)
            else:
                with feed:
                    render_round(e["log"].__dict__)

        agent = Agent(R, brain, Budget(max_rounds=S.rounds), on_event=on_event)
        try:
            out = agent.run(S.start_plan)
        except Exception as exc:  # noqa: BLE001
            status.error(f"The rehearsal stopped: {exc}")
            return
        S.agent_out = out
        audit(R, "rehearsal finished", json.dumps(out))
        status.markdown(chip("Ready for review", "review") + _esc(out["stop_reason"] or ""), unsafe_allow_html=True)
        st.button("Compare plans", type="primary", on_click=lambda: S.__setitem__("step", 3))
    elif log_file.exists():
        data = json.loads(log_file.read_text(encoding="utf-8"))
        S.agent_out = data["summary"]
        status.markdown(chip("Ready for review", "review") + _esc(data["summary"].get("stop_reason") or ""),
                        unsafe_allow_html=True)
        with feed:
            for r in data["rounds"]:
                render_round(r)
        if st.button("Compare plans", type="primary"):
            goto(3)


# ---------------------------------------------------------------- 4. Compare plans
def step_compare():
    st.subheader("4. Compare plans")
    R = rehearsal()
    out = S.agent_out
    rids = [r for r in R.run_ids()]
    best = R.best([r for r in out["runs"] if r in rids]) or out["best"]
    rows = R.compare(rids)
    cols = st.columns(min(len(rows), 4) or 1)
    for i, row in enumerate(rows):
        with cols[i % len(cols)]:
            ok = row["passes_hard_rules"]
            card(f"<h4>{row['plan']}{' · recommended' if row['run'] == best else ''}</h4>"
                 + chip("Passes hard rules" if ok else "Fails a hard rule", "pass" if ok else "fail")
                 + f"<div class='etr-num'>{row['total_extra_vehicle_hours']:,}</div>"
                   f"<div class='etr-numlabel'>vehicle-hours of extra delay (lower is better)</div>"
                   f"<div class='etr-muted'>Visitors +{row['visitor_avg_delay_min']} min per trip · others "
                   f"+{row['others_avg_extra_min']} min<br>Worst ambulance +{row['worst_ambulance_extra_min']} min · "
                   f"clears {row['minutes_to_clear']} min after the show<br>Market/residential closures "
                   f"{row['sensitive_closure_hours']} h · walk {row['walk_minutes_avg']} min · informal parking "
                   f"{int(row['informal_parking'])}</div>", best=row["run"] == best)

    st.markdown("**Recommended plan and why**")
    brain = get_brain()
    first = rids[0] if rids else None
    if S.get("summary_for") != best:
        with st.spinner("Writing the summary"):
            S.summary, S.summary_src = report.write_plan_summary(R, best, brain, compare_to=first)
            S.summary_for = best
    card(f"<p>{_esc(S.summary)}</p><div class='etr-muted'>Written by "
         f"{'Gemma, numbers checked against the results' if S.summary_src == 'gemma' else 'template'}</div>")

    pick = st.selectbox("Show on the map", rids, index=rids.index(best),
                        format_func=lambda r: f"{R.results(r)['plan_name']} ({r})")
    m = R.results(pick)
    left, right = st.columns([3, 2])
    with left:
        st_folium(maps.delay_map(m, R.plan(pick)), height=520, use_container_width=True, returned_objects=[])
        st.markdown(maps.legend_html(), unsafe_allow_html=True)
    with right:
        st.markdown("**Worst bottlenecks**")
        st.dataframe(pd.DataFrame([{"Place": b["place"], "Extra veh-h": b["extra_vehicle_hours"],
                                    "Jammed length (m)": b["jammed_length_m"],
                                    "Longest extra wait (min)": b["longest_extra_wait_min"],
                                    "When": b["worst_window"]} for b in m["bottlenecks"]]),
                     hide_index=True, width="stretch")
        st.markdown("**Ambulance trips**")
        st.dataframe(pd.DataFrame([{"Hospital": h, "Normal (min)": v["normal_min"], "This plan (min)": v["plan_min"],
                                    "Worst extra (min)": v["worst_extra_min"], "Result": "Pass" if v["pass"] else "Fail"}
                                   for h, v in m["ambulance"].items()]), hide_index=True, width="stretch")
        st.markdown("**Parking**")
        st.dataframe(pd.DataFrame([{"Lot": k, "Cars sent": v["assigned"], "Capacity": v["capacity"],
                                    "Full at": v["full_at"]} for k, v in m["parking"].items()]),
                     hide_index=True, width="stretch")
        st.markdown("**The plan**")
        for x in R.plan(pick).plain_lines():
            st.markdown(f"- {x}")

    st.markdown("**What if?**")
    st.caption("Ask for a change to the recommended plan. The assistant tests it and reports the result, even if it is worse.")
    q = st.text_input("For example: What if we also close the Sector 34/35 dividing road from 17:00 to 23:00?")
    if st.button("Test this idea", disabled=not q or S.role == "Viewer"):
        if not isinstance(brain, OllamaBrain):
            st.warning("Free-text questions need Gemma. Start Ollama, or describe the change as a menu action.")
        else:
            with st.spinner("Gemma is turning the question into plan changes, then testing them"):
                try:
                    reply, _ = brain.ask(
                        "Turn the officer's question into plan changes from the menu. Use exact place names from the list.",
                        f"Places:\n{places.map_summary()}\n\nMenu:\n{MENU_TEXT}\n\nQuestion: {q}\n\n"
                        'JSON: {"diagnosis": "what the officer asked", "changes": [...], "expected_effect": "", "stop": false}',
                        RoundReply)
                    rid, text = what_if(R, best, reply.changes)
                except Exception as exc:  # noqa: BLE001
                    rid, text = None, f"Could not test that: {exc}"
            S.whatif = text
            audit(R, "what-if", f"{q} -> {text}")
    if S.get("whatif"):
        card(f"<p>{_esc(S.whatif)}</p>")
    if st.button("Use the recommended plan: go to approval", type="primary"):
        S.final = best
        goto(4)


# ---------------------------------------------------------------- 5. Approve and publish
def step_approve():
    st.subheader("5. Approve and publish")
    R = rehearsal()
    rid = S.get("final") or S.agent_out["best"]
    m, plan = R.results(rid), R.plan(rid)
    appr_file = R.dir / "approval.json"
    approved = json.loads(appr_file.read_text()) if appr_file.exists() else None
    if approved and approved.get("run") == rid:
        st.markdown(chip("Approved", "approved") + f"<span class='etr-muted'>by {approved['role']} at "
                    f"{approved['time']}</span>", unsafe_allow_html=True)
    else:
        st.markdown(chip("Ready for review", "review"), unsafe_allow_html=True)
    if not m["passes_hard_rules"]:
        st.error("This plan fails a hard rule (ambulance access or gridlock). Approve only after checking why.")
    card(f"<h4>{m['plan_name']}</h4>" + "".join(f"<div>• {_esc(x)}</div>" for x in plan.plain_lines()))
    brain = get_brain()
    if S.get("advisory_for") != rid:
        with st.spinner("Drafting the advisory in English, Hindi and Punjabi"):
            S.advisory, S.advisory_src = report.draft_advisory(R, rid, brain)
            S.advisory_for = rid
    st.caption("Draft by " + ("Gemma (checked: every place and number comes from the plan)"
                              if S.advisory_src == "gemma" else "template") + ". Edit before approving.")
    tabs = st.tabs(["English", "हिन्दी", "ਪੰਜਾਬੀ"])
    edited = {}
    for tab, lang in zip(tabs, ["english", "hindi", "punjabi"]):
        with tab:
            edited[lang] = st.text_area(lang.title(), S.advisory[lang], height=260, key=f"adv_{lang}",
                                        disabled=S.role == "Viewer")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Approve plan and advisory", type="primary", disabled=S.role != "Approver"):
        rec = {"run": rid, "plan": m["plan_name"], "role": S.role,
               "time": dt.datetime.now().isoformat(timespec="seconds"), "advisory": edited}
        appr_file.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        audit(R, "approved", f"{rid} {m['plan_name']}")
        st.rerun()
    if S.role != "Approver":
        c1.caption("Only an Approver can approve. Switch role in the sidebar for the demo.")
    text = "\n\n".join(f"--- {k.upper()} ---\n{v}" for k, v in edited.items())
    c2.download_button("Download advisory", text.encode("utf-8"), file_name=f"advisory_{R.scn.id}.txt",
                       disabled=not (approved and approved.get("run") == rid))
    c3.download_button("Download plan", json.dumps({"plan": plan.model_dump(), "results": metrics.headline(m)},
                                                   indent=1).encode(), file_name=f"plan_{R.scn.id}_{rid}.json")
    log_md = R.dir / "decision_log.md"
    if log_md.exists():
        c4.download_button("Download decision log", log_md.read_bytes(), file_name=f"decision_log_{R.scn.id}.md")
    audit_file = R.dir / "audit_log.jsonl"
    if audit_file.exists():
        with st.expander("Audit log"):
            st.dataframe(pd.DataFrame([json.loads(x) for x in audit_file.read_text().splitlines() if x.strip()]),
                         hide_index=True, width="stretch")


# ---------------------------------------------------------------- router
if S.step == 0 or "scenario" not in S:
    S.step = 0
    step_describe()
elif S.step == 1:
    step_check()
elif S.step == 2:
    step_rehearse()
elif S.step == 3 and S.get("agent_out"):
    step_compare()
elif S.step == 4 and S.get("agent_out"):
    step_approve()
else:
    goto(2)
