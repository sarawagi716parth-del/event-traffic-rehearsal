"""The rehearsal loop (docs/03-agent-design.md, "How one rehearsal runs").

Round 1 tests the starting plan. Each later round: Gemma reads the results,
names the worst bottleneck, makes 1 to 3 changes to the best plan so far,
and the simulator tests the new plan. Limits are enforced here in code, not
by the model (guardrail 5).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from sim import metrics, places, runner
from sim.models import Plan
from sim.rehearsal import Rehearsal

from .brain import BrainError, OllamaBrain, RuleBrain
from .menu import MENU_TEXT, MenuError, apply_change
from .schemas import Change, RoundReply

SYSTEM = """You are a traffic planning assistant for a city police department.
Your job: find the traffic plan for the disruptions below that keeps the total extra delay lowest,
while following the hard rules.

Hard rules:
1. Ambulance trips to protected hospitals must stay within the limit.
2. Plans that cause gridlock are rejected.

Tie-breakers, in order: fewer closure hours in residential and market areas, faster clearing after
the show, shorter walks from parking.

Use only actions from the menu and place names from the places list.
Make at most 3 changes per round. Only quote numbers from the results you are given.
Reply only with JSON: {"diagnosis": "...", "changes": [{"action": "...", "args": {...}, "reason": "..."}],
"expected_effect": "...", "stop": false}"""


@dataclass
class Budget:
    max_rounds: int = 5
    max_runs: int = 15
    max_minutes: float = 30.0
    min_gain: float = 0.05  # stop when the main score improves by less than 5% two rounds in a row


@dataclass
class RoundLog:
    round: int
    run_id: str | None
    plan_name: str
    changes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    diagnosis: str = ""
    expected: str = ""
    result: str = ""
    headline: dict = field(default_factory=dict)
    retries: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    skipped: bool = False
    brain: str = ""


NUM = re.compile(r"(?<![\w:])-?\d+(?:[.,]\d+)?(?![\w:])")


def numbers_in(text: str) -> set[float]:
    out = set()
    for tok in NUM.findall(text or ""):
        try:
            out.add(round(float(tok.replace(",", "")), 1))
        except ValueError:
            pass
    return out


def check_numbers(text: str, allowed: set[float]) -> list[str]:
    """Guardrail 4: every number the model writes must come from the results it was given.
    Small counts (0-5, like '3 changes') are always allowed."""
    bad = []
    for n in numbers_in(text):
        if abs(n) <= 5:
            continue
        if not any(abs(n - a) <= max(0.15, 0.011 * abs(a)) for a in allowed):
            bad.append(str(n))
    return bad


def results_table(R: Rehearsal, rids: list[str]) -> str:
    rows = []
    for rid in rids:
        m = R.results(rid)
        h = metrics.headline(m)
        bn = "; ".join(f"{b['place']} {b['extra_vehicle_hours']} veh-h, queue {b['jammed_length_m']} m, "
                       f"wait +{b['longest_extra_wait_min']} min at {b['worst_window']}" for b in m["bottlenecks"][:3])
        amb = "; ".join(f"{k} +{v['worst_extra_min']} min ({'pass' if v['pass'] else 'FAIL'})"
                        for k, v in m["ambulance"].items())
        lots = "; ".join(f"{k} {v['assigned']}/{v['capacity']}" for k, v in m["parking"].items())
        rows.append(
            f"[{rid}] {m['plan_name']}: total extra delay {h['total_extra_vehicle_hours']} vehicle-hours; "
            f"visitors +{h['visitor_avg_delay_min']} min/trip; others +{h['others_avg_extra_min']} min/trip; "
            f"clear {h['minutes_to_clear']} min after show; closure hours in market/residential "
            f"{h['sensitive_closure_hours']}; walk {h['walk_minutes_avg']} min; informal parking "
            f"{h['informal_parking']}; stuck-vehicle jumps {h['jump_share_pct']}% "
            f"({'GRIDLOCK' if h['gridlock'] else 'ok'})\n   worst bottlenecks: {bn}\n   ambulances: {amb}\n"
            f"   parking used/capacity: {lots}")
    return "\n".join(rows)


def build_prompt(R: Rehearsal, best_rid: str, all_rids: list[str], tried: list[str]) -> str:
    scn = R.scn
    ev = scn.events[0]
    plan = R.plan(best_rid)
    scen = {"event": ev.name, "venue": ev.venue, "date": ev.date, "arrivals_from": ev.arrival_start,
            "show": f"{ev.show_start}-{ev.show_end}", "crowd": ev.crowd, "visitor_vehicles": ev.vehicles(),
            "visitors_from": ev.origin_shares, "protected_hospitals": scn.protected_hospitals,
            "ambulance_limit_min": scn.ambulance_limit_min}
    return (f"Scenario: {json.dumps(scen)}\n\n"
            f"Places:\n{places.map_summary()}\n\n"
            f"Menu:\n{MENU_TEXT}\n\n"
            f"Results so far:\n{results_table(R, all_rids)}\n\n"
            f"Best plan so far is [{best_rid}]. Your changes are applied to it:\n- "
            + "\n- ".join(plan.plain_lines()) +
            (f"\n\nAlready tried (do not repeat): {'; '.join(tried[-12:])}" if tried else "") +
            "\n\nDiagnose the worst problem in the best plan, then make 1 to 3 changes.")


def describe_result(prev: dict, new: dict, scn) -> str:
    a, b = metrics.headline(prev), metrics.headline(new)
    if a["total_extra_vehicle_hours"]:
        pct = 100 * (b["total_extra_vehicle_hours"] - a["total_extra_vehicle_hours"]) / abs(a["total_extra_vehicle_hours"])
    else:
        pct = 0.0
    parts = [f"Total extra delay {a['total_extra_vehicle_hours']} -> {b['total_extra_vehicle_hours']} "
             f"vehicle-hours ({pct:+.0f}%)."]
    if prev["bottlenecks"]:
        top = prev["bottlenecks"][0]["place"]
        after = next((j for j in new["all_junctions"] if j["place"] == top), None)
        if after:
            parts.append(f"{top} queue {prev['bottlenecks'][0]['jammed_length_m']} m -> {after['jammed_length_m']} m.")
    if new["bottlenecks"]:
        parts.append(f"Worst now: {new['bottlenecks'][0]['place']}.")
    parts.append(f"Ambulance limit: {'passed' if new['ambulance_pass'] else 'FAILED'}.")
    if new["gridlock"]:
        parts.append("GRIDLOCK: plan rejected.")
    return " ".join(parts)


class Agent:
    def __init__(self, R: Rehearsal, brain=None, budget: Budget | None = None, on_event=None):
        self.R = R
        self.brain = brain or RuleBrain()
        self.budget = budget or Budget()
        self.on_event = on_event or (lambda e: None)
        self.log: list[RoundLog] = []
        self.runs_used = 0
        self.t0 = None

    def _emit(self, **e):
        self.on_event(e)

    def _out_of_budget(self) -> str | None:
        if len(self.log) >= self.budget.max_rounds:
            return f"Reached the round limit ({self.budget.max_rounds})."
        if self.runs_used + len(self.R.seeds) > self.budget.max_runs:
            return f"Reached the simulation run limit ({self.budget.max_runs})."
        if (time.time() - self.t0) / 60 > self.budget.max_minutes:
            return f"Reached the time limit ({self.budget.max_minutes:.0f} minutes)."
        return None

    def run(self, start_plan: Plan) -> dict:
        self.t0 = time.time()
        R = self.R
        self._emit(type="status", text="Running the normal evening for comparison")
        R.ensure_normal()

        # Round 1: the starting plan as it is
        self._emit(type="status", text=f"Round 1: testing {start_plan.name}")
        rid = R.run_plan(start_plan, label="round 1")
        self.runs_used += len(R.seeds)
        rids, best = [rid], rid
        entry = RoundLog(1, rid, start_plan.name, changes=["Starting plan, unchanged"],
                         result=describe_result(R.results(rid), R.results(rid), R.scn).split(" Ambulance")[0],
                         headline=metrics.headline(R.results(rid)), brain=self.brain.label)
        entry.result = (f"Total extra delay {entry.headline['total_extra_vehicle_hours']} vehicle-hours. "
                        f"Worst bottleneck: {R.results(rid)['bottlenecks'][0]['place'] if R.results(rid)['bottlenecks'] else 'none'}. "
                        f"Ambulance limit: {'passed' if R.results(rid)['ambulance_pass'] else 'FAILED'}.")
        self.log.append(entry)
        self._emit(type="round", log=entry)
        tried: list[str] = []
        small_gains = 0
        stop_reason = None

        while True:
            stop_reason = self._out_of_budget()
            if stop_reason:
                break
            n = len(self.log) + 1
            self._emit(type="status", text=f"Round {n}: Gemma is reading the results" if self.brain.kind == "gemma"
                       else f"Round {n}: choosing changes")
            best_plan = R.plan(best)
            prompt = build_prompt(R, best, rids, tried)
            allowed = numbers_in(prompt)
            applied_plan, descs, rejected = None, [], []

            def validate(reply: RoundReply):
                nonlocal applied_plan, descs, rejected
                bad = check_numbers(reply.diagnosis + " " + reply.expected_effect, allowed)
                if bad:
                    raise ValueError(f"These numbers are not in the results: {', '.join(bad)}. "
                                     "Only quote numbers from the results.")
                p, ds, rej = best_plan, [], []
                for ch in reply.changes:
                    try:
                        p, d = apply_change(p, ch, R.scn)
                        ds.append(d)
                    except MenuError as exc:
                        rej.append(f"{ch.action}: {exc}")
                if reply.changes and not ds:
                    raise ValueError("None of the changes are valid: " + " | ".join(rej))
                applied_plan, descs, rejected = p, ds, rej

            retries = []
            try:
                if isinstance(self.brain, OllamaBrain):
                    reply, retries = self.brain.ask(SYSTEM, prompt, RoundReply, retries=2, validate=validate)
                else:
                    ctx = {"best_metrics": R.results(best), "best_plan": best_plan, "places": places.all_places(),
                           "tried": tried, "venue": R.scn.events[0].venue,
                           "arrival_start": R.scn.events[0].arrival_start}
                    reply = self.brain.propose(ctx)
                    validate(reply)
            except (BrainError, ValueError) as exc:
                entry = RoundLog(n, None, "", diagnosis="", skipped=True, brain=self.brain.label,
                                 result=f"Round skipped: {exc}", retries=retries)
                self.log.append(entry)
                self._emit(type="round", log=entry)
                continue

            if reply.stop or not descs:
                stop_reason = "The agent found nothing more to change."
                if reply.diagnosis:
                    self.log[-1].result += f" Next: {reply.diagnosis}"
                break

            for ch in reply.changes:
                tried.append(json.dumps([ch.action, ch.args], sort_keys=True))
            applied_plan.name = f"Plan {chr(ord('A') + len(rids))}"
            applied_plan.description = "; ".join(descs)
            self._emit(type="status", text=f"Round {n}: testing {applied_plan.name}: {applied_plan.description}")
            new_rid = R.run_plan(applied_plan, label=f"round {n}")
            self.runs_used += len(R.seeds)
            rids.append(new_rid)
            prev_m, new_m = R.results(best), R.results(new_rid)
            entry = RoundLog(n, new_rid, applied_plan.name, changes=descs,
                             reasons=[c.reason for c in reply.changes], diagnosis=reply.diagnosis,
                             expected=reply.expected_effect, result=describe_result(prev_m, new_m, R.scn),
                             headline=metrics.headline(new_m), retries=retries, rejected=rejected,
                             brain=self.brain.label)
            old_score = metrics.headline(prev_m)["total_extra_vehicle_hours"]
            new_best = R.best([best, new_rid])
            if new_best == new_rid:
                gain = (old_score - new_m["total_extra_vehicle_hours"]) / max(abs(old_score), 1e-6)
                entry.result += f" Kept: this is now the best plan."
                best = new_rid
            else:
                gain = 0.0
                entry.result += f" Not kept: the next round starts again from {R.results(best)['plan_name']}."
            small_gains = small_gains + 1 if gain < self.budget.min_gain else 0
            self.log.append(entry)
            self._emit(type="round", log=entry)
            if small_gains >= 2:
                stop_reason = "The main score improved by less than 5% two rounds in a row."
                break

        self._emit(type="status", text="Done. " + (stop_reason or ""))
        out = {"best": R.best(rids), "runs": rids, "stop_reason": stop_reason, "brain": self.brain.label,
               "runs_used": self.runs_used, "minutes": round((time.time() - self.t0) / 60, 1)}
        save_log(R, self.log, out)
        return out


def what_if(R: Rehearsal, base_rid: str, changes: list[Change]) -> tuple[str | None, str]:
    """The officer asks "What if we ...?". The agent tests it and reports honestly, even if worse."""
    plan = R.plan(base_rid)
    descs = []
    for ch in changes:
        try:
            plan, d = apply_change(plan, ch, R.scn)
            descs.append(d)
        except MenuError as exc:
            return None, f"Could not test that: {exc}"
    plan.name = f"What-if on {R.results(base_rid)['plan_name']}"
    plan.description = "; ".join(descs)
    rid = R.run_plan(plan, label="what-if")
    text = describe_result(R.results(base_rid), R.results(rid), R.scn)
    verdict = "better" if metrics.rank_key(R.results(rid)) < metrics.rank_key(R.results(base_rid)) else "worse"
    return rid, f"{plan.description}. Result: {text} Overall this is {verdict} than {R.results(base_rid)['plan_name']}."


def save_log(R: Rehearsal, log: list[RoundLog], summary: dict):
    runner.save_json({"summary": summary, "rounds": [l.__dict__ for l in log]}, R.dir / "decision_log.json")
    lines = [f"# Decision log: {R.scn.title}", "",
             f"Brain: {summary['brain']}. Runs used: {summary['runs_used']}. Minutes: {summary['minutes']}. "
             f"Stopped because: {summary['stop_reason']}", ""]
    for l in log:
        lines.append(f"## Round {l.round}" + (f" ({l.plan_name}, run {l.run_id})" if l.run_id else ""))
        lines.append("```")
        if l.skipped:
            lines.append(f"Skipped:  {l.result}")
        else:
            lines.append("Change:   " + "; ".join(l.changes))
            if l.reasons:
                lines.append("Reason:   " + " ".join(r for r in l.reasons if r))
            if l.diagnosis:
                lines.append("Diagnosis: " + l.diagnosis)
            if l.expected:
                lines.append("Expected: " + l.expected)
            lines.append("Result:   " + l.result)
            if l.rejected:
                lines.append("Rejected by the menu check: " + " | ".join(l.rejected))
            if l.retries:
                lines.append("Format retries: " + " | ".join(l.retries))
        lines.append("```")
        lines.append("")
    (R.dir / "decision_log.md").write_text("\n".join(lines), encoding="utf-8")
