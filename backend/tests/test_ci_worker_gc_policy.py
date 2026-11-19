"""Real isolated collectors retain reclamation and caller configuration in CI."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_worker_gc.py"
PROBE = r'''
import gc, importlib.util, json, sys, weakref
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location("worker_policy",sys.argv[1])
policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
mode=sys.argv[2]
original=(1700,9,11) if mode=="custom" else (700,10,10)
gc.enable();gc.collect();gc.set_threshold(*original)
cleanups=[]
config=SimpleNamespace(add_cleanup=cleanups.append)
if mode!="master":config.workerinput={"workerid":"synthetic-gc-control"}
session=SimpleNamespace(config=config)
policy.pytest_sessionstart(session)
active=gc.get_threshold()
if mode in ("worker","repeat"):
 assert active==(14000,10,10) and gc.isenabled() and all(active)
 if mode=="repeat":
  policy.pytest_sessionstart(session);assert gc.get_threshold()==active and len(cleanups)==1
 class Cycle:
  def __init__(self):self.link=self
 refs=[]
 # Unreachable cycles are collected automatically at the actual CI threshold.
 for _ in range(30000):
  item=Cycle();refs.append(weakref.ref(item));del item
 automatic=sum(ref() is None for ref in refs)
 assert automatic>0 and gc.isenabled()
 item=Cycle();ref=weakref.ref(item);del item
 gc.collect()
 assert ref() is None
 for cleanup in reversed(cleanups):cleanup()
 assert gc.get_threshold()==original and gc.isenabled()
else:
 assert active==original and not cleanups and gc.isenabled()
 automatic=0
print(json.dumps({"mode":mode,"active":active,"restored":gc.get_threshold(),
                  "automatic_reclaimed":automatic,"automatic_enabled":gc.isenabled()}))
'''


@pytest.mark.parametrize("mode", ["outside", "master", "custom", "worker", "repeat"])
def test_real_collector_contract_in_clean_child(mode):
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONNOUSERSITE": "1"}
    if mode != "outside":
        environment["GITHUB_ACTIONS"] = "true"
    result = subprocess.run([sys.executable, "-c", PROBE, str(SCRIPT), mode],
                            env=environment, capture_output=True, timeout=10, check=True, text=True)
    proof = json.loads(result.stdout)
    assert proof["mode"] == mode and proof["automatic_enabled"]
    if mode in ("worker", "repeat"):
        assert proof["automatic_reclaimed"] > 0 and proof["restored"] == [700, 10, 10]
