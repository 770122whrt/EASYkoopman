import json
import subprocess
import sys
from pathlib import Path

from workflows.collector_exit_v28 import guarded_exit_code


def test_native_exit_zero_cannot_pass_failed_missing_or_foreign_trace():
    q = {'case': 'test'}; source = 'a'*40
    good = dict(status='completed_calibration_pending_acceptance', request=q,
                source_commit=source, training_eligible=False, model_fits=0)
    assert guarded_exit_code(0, good, q, source) == 0
    assert guarded_exit_code(7, good, q, source) == 7
    for bad in (None, {}, dict(good, status='failed_calibration'),
                dict(good, source_commit='b'*40), dict(good, training_eligible=True)):
        assert guarded_exit_code(0, bad, q, source) == 1


def test_outer_exit_survives_child_native_termination(tmp_path):
    trace = tmp_path/'trace.json'
    child = 'import json,os,sys;open(sys.argv[1],"w").write(json.dumps({"status":"failed_calibration"}));os._exit(0)'
    native = subprocess.run([sys.executable, '-c', child, str(trace)])
    assert native.returncode == 0
    assert guarded_exit_code(native.returncode, json.loads(trace.read_text()), {}, 'a'*40) == 1
