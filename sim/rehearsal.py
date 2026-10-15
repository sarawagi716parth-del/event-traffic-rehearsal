"""One rehearsal on disk: the scenario, the normal evening and every plan run.

runs/<scenario id>/
    scenario.json
    normal/seed11/raw.pkl.gz ...      the normal evening, run once per seed
    r01/plan.json, metrics.json, seed11/raw.pkl.gz ...
    decision_log.md, decision_log.json
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import config, metrics, runner
from .models import Plan, Scenario


class Rehearsal:
    def __init__(self, scn: Scenario, seeds=None, net_name: str | None = None, root: Path | None = None):
        self.scn = scn
        self.seeds = list(seeds or config.DEFAULT_SEEDS)
        self.net = net_name or config.NETWORK_NAME
        self.dir = (root or config.RUNS) / scn.id
        self.dir.mkdir(parents=True, exist_ok=True)
        runner.save_json(scn.model_dump(), self.dir / "scenario.json")

    # ---------- normal evening ----------
    def _normal_key(self) -> str:
        s = self.scn
        relevant = {"normal": s.normal.model_dump(), "hosp": s.protected_hospitals, "amb": s.ambulance_every_min,
                    "win": [s.sim_begin, s.sim_end, s.rain], "net": self.net,
                    "ev": [(e.venue, e.arrival_start, e.show_end) for e in s.events]}
        return hashlib.md5(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:10]

    def normal_dir(self) -> Path:
        return self.dir / f"normal_{self._normal_key()}"

    def ensure_normal(self, progress=None):
        """Run the normal evening once per seed (step 0 of a rehearsal). Cached."""
        d = self.normal_dir()
        missing = [s for s in self.seeds if not (d / f"seed{s}" / "raw.pkl.gz").exists()]
        if missing:
            if progress:
                progress(f"Running the normal evening for comparison ({len(missing)} runs)")
            runner.run_many(runner.jobs_for(self.scn, None, d, missing, self.net))
        return d

    def _normal_raw(self, seed):
        return runner.load_raw(self.normal_dir() / f"seed{seed}" / "raw.pkl.gz")

    # ---------- plan runs ----------
    def run_ids(self) -> list[str]:
        return sorted(p.name for p in self.dir.glob("r[0-9][0-9]") if (p / "metrics.json").exists())

    def next_id(self) -> str:
        used = [int(p.name[1:]) for p in self.dir.glob("r[0-9][0-9]")]
        return f"r{(max(used) + 1 if used else 1):02d}"

    def run_plan(self, plan: Plan, label: str = "", progress=None) -> str:
        """run_simulation(plan, seeds=3): returns the run ID."""
        self.ensure_normal(progress)
        rid = self.next_id()
        d = self.dir / rid
        d.mkdir(parents=True, exist_ok=True)
        runner.save_json(plan.model_dump(), d / "plan.json")
        if progress:
            progress(f"Testing {plan.name} ({len(self.seeds)} runs)")
        t0 = time.time()
        paths = runner.run_many(runner.jobs_for(self.scn, plan, d, self.seeds, self.net))
        per_seed = []
        for s, p in zip(self.seeds, paths):
            per_seed.append(metrics.seed_metrics(self.scn, plan, runner.load_raw(p), self._normal_raw(s), self.net))
        m = metrics.combine(self.scn, per_seed)
        m["run_id"] = rid
        m["plan_name"] = plan.name
        m["label"] = label
        m["wall_seconds"] = round(time.time() - t0, 1)
        m["edge_extra_vh"] = _avg_dict([ps["edge_extra_vh"] for ps in per_seed])
        runner.save_json(m, d / "metrics.json")
        return rid

    def results(self, rid: str) -> dict:
        """get_results(run_id)"""
        return json.loads((self.dir / rid / "metrics.json").read_text())

    def plan(self, rid: str) -> Plan:
        return Plan.model_validate_json((self.dir / rid / "plan.json").read_text())

    def compare(self, rids: list[str]) -> list[dict]:
        """compare_runs(run_ids): one row of headline numbers per run."""
        rows = []
        for rid in rids:
            m = self.results(rid)
            rows.append({"run": rid, "plan": m["plan_name"], **metrics.headline(m),
                         "passes_hard_rules": m["passes_hard_rules"]})
        return rows

    def best(self, rids=None) -> str | None:
        rids = rids or self.run_ids()
        ok = [r for r in rids if self.results(r)["passes_hard_rules"]]
        pool = ok or rids
        return min(pool, key=lambda r: metrics.rank_key(self.results(r))) if pool else None


def _avg_dict(dicts):
    keys = set().union(*dicts)
    return {k: round(sum(d.get(k, 0) for d in dicts) / len(dicts), 2) for k in keys}
