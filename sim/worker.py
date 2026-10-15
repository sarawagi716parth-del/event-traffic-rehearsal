"""Runs one simulation job in its own process: python -m sim.worker job.json"""
import json
import sys

from sim import runner

if __name__ == "__main__":
    job = json.loads(open(sys.argv[1], encoding="utf-8").read())
    print(runner.run_one(job))
