"""Output actions: the plan summary for the officer and the public advisory.

Both are drafts. The facts (roads, lots, times, numbers) come from the plan and
the run results. Gemma writes them up; every number Gemma writes is checked
against the results (guardrail 4). If Gemma is not available or its draft
fails the check, a fixed template is used instead, and the app says so.
"""
from __future__ import annotations

from sim import metrics
from sim.models import Plan
from sim.rehearsal import Rehearsal

from .brain import BrainError, OllamaBrain
from .loop import check_numbers, numbers_in
from .schemas import AdvisoryDraft, TextDraft


def facts(R: Rehearsal, rid: str) -> dict:
    m, plan = R.results(rid), R.plan(rid)
    ev = R.scn.events[0]
    starts = [c.start for c in plan.closures] + [d.start for d in plan.diversions]
    ends = [c.end for c in plan.closures] + [d.end for d in plan.diversions]
    avoid = [b["place"] for b in m["bottlenecks"][:3]]
    return {
        "event": ev.name, "venue": ev.venue, "date": ev.date,
        "from": min(starts) if starts else ev.arrival_start, "to": max(ends) if ends else "23:30",
        "closed_roads": [c.road for c in plan.closures],
        "diversions": [(d.junction, d.blocked_toward, d.send_to) for d in plan.diversions],
        "lots": plan.open_lots(), "dropoffs": plan.dropoffs,
        "shuttle_lots": [s.lot for s in plan.shuttles], "avoid": avoid,
        "assignments": [(a.origin, a.lot) for a in plan.assignments if a.share >= 0.5],
    }


# ---------------- templates (used when Gemma is not available) ----------------

def _join(xs, sep=", "):
    return sep.join(xs) if xs else "-"


def template_advisory(f: dict) -> dict:
    en = [f"Traffic advisory: {f['event']} at {f['venue']}, {f['date']}", ""]
    hi = [f"यातायात सूचना: {f['venue']} में {f['event']}, {f['date']}", ""]
    pa = [f"ਟ੍ਰੈਫਿਕ ਸੂਚਨਾ: {f['venue']} ਵਿਖੇ {f['event']}, {f['date']}", ""]
    if f["closed_roads"]:
        en.append(f"From {f['from']} to {f['to']}, these roads will be closed to general traffic: {_join(f['closed_roads'])}.")
        hi.append(f"{f['from']} से {f['to']} तक ये सड़कें आम यातायात के लिए बंद रहेंगी: {_join(f['closed_roads'])}।")
        pa.append(f"{f['from']} ਤੋਂ {f['to']} ਤੱਕ ਇਹ ਸੜਕਾਂ ਆਮ ਆਵਾਜਾਈ ਲਈ ਬੰਦ ਰਹਿਣਗੀਆਂ: {_join(f['closed_roads'])}।")
    for j, toward, send in f["diversions"]:
        to_en = f" and sent towards {send}" if send else ""
        to_hi = f" {send} की ओर" if send else ""
        to_pa = f" {send} ਵੱਲ" if send else ""
        en.append(f"Diversion: at {j}, traffic heading towards {toward} will be stopped{to_en}.")
        hi.append(f"डायवर्जन: {j} पर {toward} की ओर जाने वाला यातायात रोका जाएगा और{to_hi} मोड़ा जाएगा।")
        pa.append(f"ਡਾਇਵਰਜ਼ਨ: {j} 'ਤੇ {toward} ਵੱਲ ਜਾਣ ਵਾਲੀ ਆਵਾਜਾਈ ਰੋਕੀ ਜਾਵੇਗੀ ਅਤੇ{to_pa} ਮੋੜੀ ਜਾਵੇਗੀ।")
    en.append(f"Parking: visitors must park only at {_join(f['lots'])}. There is no parking near the venue.")
    hi.append(f"पार्किंग: कार्यक्रम में आने वाले लोग केवल इन स्थानों पर वाहन पार्क करें: {_join(f['lots'])}। आयोजन स्थल के पास पार्किंग नहीं होगी।")
    pa.append(f"ਪਾਰਕਿੰਗ: ਸਮਾਗਮ ਵਿੱਚ ਆਉਣ ਵਾਲੇ ਲੋਕ ਸਿਰਫ਼ ਇਨ੍ਹਾਂ ਥਾਵਾਂ 'ਤੇ ਵਾਹਨ ਖੜ੍ਹੇ ਕਰਨ: {_join(f['lots'])}। ਸਮਾਗਮ ਵਾਲੀ ਥਾਂ ਦੇ ਨੇੜੇ ਪਾਰਕਿੰਗ ਨਹੀਂ ਹੋਵੇਗੀ।")
    for origin, lot in f["assignments"]:
        en.append(f"Visitors coming from {origin} should use {lot}.")
        hi.append(f"{origin} से आने वाले लोग {lot} का उपयोग करें।")
        pa.append(f"{origin} ਤੋਂ ਆਉਣ ਵਾਲੇ ਲੋਕ {lot} ਦੀ ਵਰਤੋਂ ਕਰਨ।")
    if f["dropoffs"]:
        en.append(f"Cabs and autos will drop passengers at {_join(f['dropoffs'])}.")
        hi.append(f"कैब और ऑटो यात्रियों को यहाँ उतारेंगे: {_join(f['dropoffs'])}।")
        pa.append(f"ਕੈਬ ਅਤੇ ਆਟੋ ਸਵਾਰੀਆਂ ਨੂੰ ਇੱਥੇ ਉਤਾਰਨਗੇ: {_join(f['dropoffs'])}।")
    if f["shuttle_lots"]:
        en.append(f"Shuttle buses will run to the venue from {_join(f['shuttle_lots'])}.")
        hi.append(f"आयोजन स्थल के लिए शटल बसें यहाँ से चलेंगी: {_join(f['shuttle_lots'])}।")
        pa.append(f"ਸਮਾਗਮ ਵਾਲੀ ਥਾਂ ਲਈ ਸ਼ਟਲ ਬੱਸਾਂ ਇੱਥੋਂ ਚੱਲਣਗੀਆਂ: {_join(f['shuttle_lots'])}।")
    if f["avoid"]:
        en.append(f"Commuters not attending the event should avoid {_join(f['avoid'])}.")
        hi.append(f"कार्यक्रम में न जाने वाले यात्री इन स्थानों से बचें: {_join(f['avoid'])}।")
        pa.append(f"ਸਮਾਗਮ ਵਿੱਚ ਨਾ ਜਾਣ ਵਾਲੇ ਯਾਤਰੀ ਇਨ੍ਹਾਂ ਥਾਵਾਂ ਤੋਂ ਬਚਣ: {_join(f['avoid'])}।")
    en.append("Emergency vehicles will be allowed through at all times.")
    hi.append("आपातकालीन वाहनों को हर समय जाने दिया जाएगा।")
    pa.append("ਐਮਰਜੈਂਸੀ ਵਾਹਨਾਂ ਨੂੰ ਹਰ ਸਮੇਂ ਲੰਘਣ ਦਿੱਤਾ ਜਾਵੇਗਾ।")
    return {"english": "\n".join(en), "hindi": "\n".join(hi), "punjabi": "\n".join(pa)}


def template_summary(R: Rehearsal, rid: str, compare_to: str | None) -> str:
    m = R.results(rid)
    h = metrics.headline(m)
    lines = [f"Recommended: {m['plan_name']}."]
    if compare_to and compare_to != rid:
        b = metrics.headline(R.results(compare_to))
        lines.append(f"Total extra delay is {h['total_extra_vehicle_hours']} vehicle-hours, against "
                     f"{b['total_extra_vehicle_hours']} for {R.results(compare_to)['plan_name']}.")
    else:
        lines.append(f"Total extra delay is {h['total_extra_vehicle_hours']} vehicle-hours.")
    lines.append(f"Visitors lose {h['visitor_avg_delay_min']} minutes per trip on average; other road users "
                 f"lose {h['others_avg_extra_min']} minutes per trip.")
    lines.append(f"Ambulances: worst extra time {h['worst_ambulance_extra_min']} minutes "
                 f"({'within' if m['ambulance_pass'] else 'OVER'} the limit of {R.scn.ambulance_limit_min} minutes).")
    lines.append(f"Roads near the venue clear {h['minutes_to_clear']} minutes after the show.")
    if m["bottlenecks"]:
        lines.append(f"Watch {m['bottlenecks'][0]['place']}: the worst queue in this plan.")
    if not m["passes_hard_rules"]:
        lines.append("Warning: no tested plan passed every hard rule. This is the least bad one.")
    return " ".join(lines)


# ---------------- Gemma versions ----------------

def write_plan_summary(R: Rehearsal, rid: str, brain, compare_to: str | None = None) -> tuple[str, str]:
    """Returns (text, source) where source is 'gemma' or 'template'."""
    base = template_summary(R, rid, compare_to)
    if not isinstance(brain, OllamaBrain):
        return base, "template"
    plan: Plan = R.plan(rid)
    ctx = (f"Facts (use only these numbers):\n{base}\n\nPlan:\n- " + "\n- ".join(plan.plain_lines()))
    allowed = numbers_in(ctx)

    def validate(d: TextDraft):
        bad = check_numbers(d.text, allowed)
        if bad:
            raise ValueError(f"Numbers not in the facts: {', '.join(bad)}")

    try:
        d, _ = brain.ask("You write short, plain briefings for police officers. No jargon. 4 to 6 sentences.",
                         ctx + "\n\nWrite why this plan is recommended and what to watch. JSON: {\"text\": \"...\"}",
                         TextDraft, validate=validate)
        return d.text, "gemma"
    except BrainError:
        return base, "template"


def draft_advisory(R: Rehearsal, rid: str, brain) -> tuple[dict, str]:
    f = facts(R, rid)
    base = template_advisory(f)
    if not isinstance(brain, OllamaBrain):
        return base, "template"
    allowed = numbers_in(base["english"])
    must_have = f["lots"] + f["closed_roads"]

    def validate(d: AdvisoryDraft):
        for lang in ("english", "hindi", "punjabi"):
            bad = check_numbers(getattr(d, lang), allowed)
            if bad:
                raise ValueError(f"{lang}: numbers not in the plan: {', '.join(bad)}")
        missing = [x for x in must_have if x.split(",")[0] not in d.english]
        if missing:
            raise ValueError(f"english draft leaves out: {', '.join(missing)}")

    try:
        d, _ = brain.ask(
            "You write public traffic advisories for a city police department in English, Hindi (Devanagari) "
            "and Punjabi (Gurmukhi). Keep place names exactly as given, in English. Plain, short sentences.",
            "Rewrite this advisory clearly. Keep every road, lot, place and time. Add nothing new.\n\n"
            + base["english"] + '\n\nJSON: {"english": "...", "hindi": "...", "punjabi": "..."}',
            AdvisoryDraft, validate=validate)
        return d.model_dump(), "gemma"
    except BrainError:
        return base, "template"
