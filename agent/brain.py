"""The agent's brain: Gemma 4 through Ollama, running on this machine.

Gemma must answer in a fixed JSON format. If a reply does not parse or does
not match the format, the error goes back to Gemma for up to 2 retries
(guardrail 1). Nothing is sent outside this machine.

RuleBrain is a simple fixed-rule stand-in. It is used only when Ollama is not
running (and for automated tests). The app labels its output clearly.
"""
from __future__ import annotations

import json
import os
import re

from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = os.environ.get("ETR_MODEL", "gemma4:e4b-it-qat")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


class BrainError(RuntimeError):
    pass


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text


class OllamaBrain:
    kind = "gemma"

    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.2, num_ctx: int = 8192):
        import ollama

        self.model = model
        self.client = ollama.Client(host=OLLAMA_HOST)
        self.options = {"temperature": temperature, "num_ctx": num_ctx}
        self.label = f"Gemma ({model})"
        self.calls = 0

    @staticmethod
    def available(model: str = DEFAULT_MODEL) -> tuple[bool, str]:
        try:
            import ollama

            names = [m.model for m in ollama.Client(host=OLLAMA_HOST).list().models]
            if model in names or any(n.startswith(model) for n in names):
                return True, f"{model} ready"
            return False, f"Ollama is running but {model} is not pulled. Found: {', '.join(names) or 'none'}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Ollama not reachable ({exc.__class__.__name__})"

    def ask(self, system: str, user: str, model_cls: type[BaseModel], retries: int = 2,
            validate=None) -> tuple[BaseModel, list[str]]:
        """Ask Gemma for JSON matching `model_cls`. `validate` can raise ValueError for
        extra checks (unknown place names, invented numbers); that error is sent back too."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        errors = []
        for attempt in range(retries + 1):
            self.calls += 1
            resp = self.client.chat(model=self.model, messages=messages,
                                    format=model_cls.model_json_schema(), options=self.options)
            text = resp.message.content or ""
            try:
                obj = model_cls.model_validate_json(_strip_fences(text))
                if validate:
                    validate(obj)
                return obj, errors
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                msg = str(exc).splitlines()[0][:400] if not isinstance(exc, ValidationError) else \
                    "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
                errors.append(f"attempt {attempt + 1}: {msg}")
                messages += [{"role": "assistant", "content": text[:2000]},
                             {"role": "user", "content": f"That reply was rejected: {msg}. "
                                                         "Reply again with corrected JSON only."}]
        raise BrainError("Gemma's reply failed the checks 3 times: " + " | ".join(errors))


class RuleBrain:
    """A fixed-rule stand-in for testing without Gemma. Not AI."""

    kind = "rules"
    label = "Fixed rules (no AI; Ollama not running)"
    calls = 0

    def propose(self, ctx: dict):
        """Returns a RoundReply-like dict built from simple rules about the latest results."""
        from .schemas import Change, RoundReply

        m, plan, pl = ctx["best_metrics"], ctx["best_plan"], ctx["places"]
        tried = ctx["tried"]
        venue = ctx["venue"]
        changes, why = [], []
        top = m["bottlenecks"][0] if m["bottlenecks"] else None

        def new(action, args, reason):
            key = json.dumps([action, args], sort_keys=True)
            if key in tried or len(changes) >= 2:
                return
            changes.append(Change(action=action, args=args, reason=reason))

        # Rule 1: closures that start long before visitors arrive only hurt shops and residents
        arrive = ctx["arrival_start"]
        for c in plan.closures:
            if c.start < arrive:
                new("close_road", {"road": c.road, "start": arrive, "end": c.end, "allow": c.allow},
                    f"{c.road} closes at {c.start}, before visitors start arriving at {arrive}.")
        # Rule 2: overflow parking -> open the nearest unused lot
        open_lots = set(plan.open_lots())
        if m["informal_parking"] > 0 or any(v["full_at"] != "not full" for v in m["parking"].values()):
            spare = sorted((n for n, p in pl.items() if p["kind"] == "parking" and n not in open_lots),
                           key=lambda n: pl[n]["dist_from_venue_km"].get(venue, 99))
            if spare:
                new("open_parking", {"lot": spare[0]}, "Lots are filling up and visitors park informally.")
        # Rule 3: a diversion or closure at the worst junction -> remove it
        if top:
            for d in plan.diversions:
                if top["place"] in (d.junction, d.blocked_toward, d.send_to):
                    new("remove_diversion", {"junction": d.junction},
                        f"{top['place']} is the worst bottleneck and the diversion there sends traffic into it.")
            for c in plan.closures:
                road = pl.get(c.road, {})
                if top["place"] in (road.get("from"), road.get("to")):
                    new("open_road", {"road": c.road}, f"{top['place']} is the worst bottleneck at the end of {c.road}.")
        # Rule 4: the most loaded lot -> move one direction's visitors to the emptiest lot
        loads = {k: v["assigned"] / max(v["capacity"], 1) for k, v in m["parking"].items()}
        if len(loads) >= 2:
            busy = max(loads, key=loads.get)
            quiet = min(loads, key=loads.get)
            origins = [n for n, p in pl.items() if p["kind"] == "origin" and not p.get("interior")]
            if busy != quiet and origins:
                o = min(origins, key=lambda n: _dist(pl[n]["xy"], pl[quiet]["xy"]))
                new("assign_arrivals", {"origin": o, "lot": quiet, "share": 1.0},
                    f"{busy} is the fullest lot; {quiet} has room and is closest to visitors from {o}.")
        if not changes:
            return RoundReply(diagnosis="No rule applies any more.", changes=[], expected_effect="", stop=True)
        diag = (f"The worst bottleneck is {top['place']} with {top['extra_vehicle_hours']} extra vehicle-hours."
                if top else "No major bottleneck.")
        return RoundReply(diagnosis=diag, changes=changes,
                          expected_effect="Less delay near the venue.", stop=False)


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def get_brain(prefer: str = "gemma", model: str = DEFAULT_MODEL):
    if prefer == "gemma":
        ok, _ = OllamaBrain.available(model)
        if ok:
            return OllamaBrain(model)
    return RuleBrain()
