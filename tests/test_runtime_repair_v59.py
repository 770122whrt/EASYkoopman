"""Actual reset regression and shutdown boundaries; no simulated-physics claim."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from test_prepared_projected_v40 import context
from test_runtime_episode_v57 import snapshot, NAMES

ROOT = Path(__file__).resolve().parents[1]
RAW = 'docs/evidence/phase9/server-preflight-v58-20260920/remote/results/p9-v57-base/trace-before-cleanup.json'


def real_snapshot():
    return json.loads((ROOT / RAW).read_text(encoding='utf-8'))['reset_record']['snapshot']


def actual_shape_fixture(name):
    data = snapshot(name)
    t = data['telemetry']
    t['thruster_dynamics_time_constant_s'] = [t['thruster_dynamics_time_constant_s'][0][0]]
    t['drag_multiplier'] = [t['drag_multiplier'][0][0]]
    return data


def test_actual_reset_is_accepted_without_changing_observed_data_or_old_failure():
    from workflows.runtime_episode_v59 import check_runtime_context
    from workflows.runtime_episode_v57 import check_runtime_context as old
    data = real_snapshot(); original = deepcopy(data)
    with pytest.raises(ValueError, match='shape_or_finite'):
        old(data, 'base', context())
    result = check_runtime_context(data, 'base', context())
    assert result['accepted'] and data == original
    assert result['actuator_tau_s'] == pytest.approx(.05)


@pytest.mark.parametrize('name', NAMES)
def test_single_environment_scalars_for_every_supported_topology(name):
    from workflows.runtime_episode_v59 import check_runtime_context
    assert check_runtime_context(actual_shape_fixture(name), name, context(name))['accepted']


@pytest.mark.parametrize('field', ['thruster_dynamics_time_constant_s', 'drag_multiplier'])
@pytest.mark.parametrize('bad', [[], [[.05]], [.05, .05], [[.05] * 8], [float('nan')], [float('inf')], .05])
def test_scalar_contract_rejects_arbitrary_shapes_and_nonfinite_values(field, bad):
    from workflows.runtime_episode_v59 import check_runtime_context
    data = actual_shape_fixture('base'); data['telemetry'][field] = bad
    with pytest.raises(ValueError, match='runtime_context'):
        check_runtime_context(data, 'base', context())


@pytest.mark.parametrize('bad', ['tau', 'drag', 'mass', 'mask', 'gravity', 'inertia'])
def test_actual_shape_fix_does_not_relax_physical_or_topology_gates(bad):
    from workflows.runtime_episode_v59 import check_runtime_context
    data = actual_shape_fixture('base'); t = data['telemetry']; b = data['backend']
    if bad == 'tau': t['thruster_dynamics_time_constant_s'][0] += .01
    if bad == 'drag': t['drag_multiplier'][0] += 1
    if bad == 'mass': b['mass_kg'][0][0] += 1
    if bad == 'mask': t['control_mask_4'][0][0] = 0
    if bad == 'gravity': b['gravity_world_m_s2'][2] = 0
    if bad == 'inertia': b['inertia_9'][0][1] = .1
    with pytest.raises(ValueError, match='runtime_context'):
        check_runtime_context(data, 'base', context())


def test_app_launch_explicitly_disables_native_fast_shutdown():
    from workflows.collect_runtime_v59 import launch_application
    seen = []; token = object()
    def factory(options):
        seen.append(options)
        return SimpleNamespace(app=token)
    assert launch_application(factory) is token
    assert seen == [{'headless': True, 'fast_shutdown': False}]


def test_cleanup_records_boundaries_and_preserves_original_failure(tmp_path):
    from workflows.collect_runtime_v59 import close_resources
    report = {'status': 'stopped_runtime_no_go', 'exception': 'context_failure', 'cleanup_errors': []}
    worker = SimpleNamespace(close=lambda: {'process_stopped': True, 'io_threads_stopped': True})
    def fail(): raise RuntimeError('environment-close')
    close_resources(worker, SimpleNamespace(close=fail), SimpleNamespace(close=lambda: None), report, output=tmp_path)
    assert report['exception'] == 'context_failure'
    assert report['cleanup_completed'] == {'worker': True, 'environment': False, 'simulation_app': True}
    assert report['cleanup_errors'] == ['environment:RuntimeError:environment-close']
    assert len(list(tmp_path.glob('cleanup-*.json'))) == 6


def test_native_zero_during_app_close_leaves_started_but_not_completed_evidence(tmp_path):
    code = '''
from pathlib import Path
from types import SimpleNamespace
import os,sys
from workflows.collect_runtime_v59 import close_resources
p=Path(sys.argv[1]); r={'status':'completed_runtime_pending_cleanup','cleanup_errors':[]}
w=SimpleNamespace(close=lambda:{'process_stopped':True,'io_threads_stopped':True})
close_resources(w,SimpleNamespace(close=lambda:None),SimpleNamespace(close=lambda:os._exit(0)),r,output=p)
(p/'unexpected-return').write_text('must not happen')
'''
    got = subprocess.run([sys.executable, '-B', '-c', code, str(tmp_path)], cwd=ROOT,
                         capture_output=True, timeout=20)
    assert got.returncode == 0, got.stderr
    assert (tmp_path/'cleanup-03-simulation_app-begin.json').exists()
    assert not (tmp_path/'cleanup-03-simulation_app-end.json').exists()
    assert not (tmp_path/'unexpected-return').exists()


@pytest.mark.parametrize('failure', [None, 'missing_app', 'app_not_returned', 'fast_shutdown', 'python_exit_zero'])
def test_only_returned_complete_cleanup_can_qualify_the_report(failure):
    from workflows.collect_runtime_v59 import classify_exit
    from workflows.phase9_preflight_v59 import cases
    q = cases()[0]
    r = dict(status='completed_runtime_pending_acceptance', request=q, release_sha256='a'*64,
             model_fits=0, training_eligible=False, cleanup_errors=[],
             worker_closed={'process_stopped':True,'io_threads_stopped':True},
             app_launch={'headless':True,'fast_shutdown':False},
             cleanup_completed={'worker':True,'environment':True,'simulation_app':True})
    if failure == 'missing_app': del r['cleanup_completed']['simulation_app']
    if failure == 'app_not_returned': r['cleanup_completed']['simulation_app'] = False
    if failure == 'fast_shutdown': r['app_launch']['fast_shutdown'] = True
    if failure == 'python_exit_zero': r['cleanup_errors'].append('simulation_app:SystemExit:0')
    assert (classify_exit(0,r,q,'a'*64) == 0) == (failure is None)


def test_repair_protocol_changes_identity_but_keeps_cases_and_numerical_gates():
    from workflows.phase9_preflight_v59 import proposal, cases
    from workflows.phase9_preflight_v57 import proposal as old
    new = proposal(); before = old()
    for k in before.keys() - {'schema', 'cases'}: assert new[k] == before[k], k
    for a, b in zip(cases(), before['cases']):
        assert {k:v for k,v in a.items() if k!='case_id'} == {k:v for k,v in b.items() if k!='case_id'}
        assert a['case_id'] != b['case_id']


def test_old_approval_cannot_authorize_a_repaired_release(tmp_path):
    from workflows.phase9_preflight_v59 import authorize_case, cases
    with pytest.raises(ValueError, match='approval'):
        authorize_case(tmp_path,cases()[0],{'schema':'phase9-runtime-preflight-approval-v57','approved':True})
