"""Offline startup counterfactuals. Never a plant validation or admitted controller."""
import argparse
from dataclasses import replace
import gzip
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflows.runtime_assets_v56 import AssetLocation, load_assets
from workflows.collect_runtime_v59 import HANDOFF_SHA
from workflows.identify_sparse_world_v30 import from_record, load_fit_cache
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from koopman.prepared_projected_v40 import prepare_projected
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.rate30_v67 import FEEDBACK_CONFIG
from koopman.control_objective_v44 import state_features, control_mask
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS


def encode(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    raise TypeError(type(value).__name__)


def simulate(assets, model, name, reference, *, ideal_actuator=False, axiswise=False, angular_kd=6.):
    domain, context = assets.domains[name], assets.context(name)
    predictor = prepare_projected(model, context)
    # Windows offline analysis removes scheduling confounding, not online limits.
    policy = InexactTrackingFeedback(domain, context, config=replace(FEEDBACK_CONFIG, timeout_ms=1000., angular_kd=angular_kd))
    x = np.r_[5.5, 1., np.zeros(9)]
    startup = policy.prepare_startup(x, reference)
    result = dict(configuration=name, reference=reference, ideal_actuator_counterfactual=ideal_actuator, axiswise_diagnostic=axiswise, angular_kd=angular_kd,
                  startup=startup, rows=[], stop=None, online_eligible=False)
    if startup['status'] != 'prepared':
        result['stop'] = startup['reason']; return result
    steady = policy.steady
    actuator = Float32PWMActuatorState(steady.allocator.wrench_matrix.shape[1],
        tau=EMBODIMENT_CONFIGS[name]['dyn_time_constant'], dt=1/120, clock='float32_accumulated_v1')
    previous = None
    for tick in range(60):
        decision = policy.decide(x, reference, previous=previous)
        if decision['status'] != 'ready':
            result['stop'] = decision['reason']; break
        command = decision['command']
        if axiswise and previous is not None:
            lo = np.maximum(domain.command_lower, previous.astype(float)-FEEDBACK_CONFIG.slew)
            hi = np.minimum(domain.command_upper, previous.astype(float)+FEEDBACK_CONFIG.slew)
            candidate = np.clip(decision['static_command'], lo, hi).astype(np.float32)
            checked = steady.inspect(candidate, decision['requested_wrench'], lo, hi)
            if checked['command_constraints_accepted']:
                from koopman.inexact_tracking_v66 import _score
                if _score(checked) < _score(decision['inspection']): command = candidate
        previous = command
        allocation = steady.evaluate(previous)
        for _ in range(4):
            speed = actuator.advance_pwm(allocation['pwm'])
            wrench = allocation['wrench'] if ideal_actuator else steady.allocator.wrench_matrix @ (
                steady.allocator.rotor_constant*np.abs(speed)*speed)
            x = predictor(x[None], (wrench/steady.scale)[None], context)[0]
            failure = domain.check_states(x[None])
            result['rows'].append(dict(step=len(result['rows'])+1, state=x.copy(), command=previous,
                                       wrench=wrench, rejection=failure))
            if failure: break
        if failure:
            result['stop'] = failure; break
    result['steps'] = len(result['rows'])
    result['peak_abs_roll_rate'] = max((abs(r['state'][8]) for r in result['rows']), default=0.)
    return result


def diagnose(release, trace):
    assets = load_assets(AssetLocation(str(release.resolve()), '.', 'assets/v38/inputs', HANDOFF_SHA), model_key='nonlinear__pooled')
    model = from_record(json.loads(assets.model_path.read_text()))
    with gzip.open(trace, 'rt') as stream: actual = json.load(stream)
    domain = assets.domains['asymmetric']; context = assets.context('asymmetric')
    predictor = prepare_projected(model, context)
    rows = actual['substeps']; prior = np.r_[5.5, 1., np.zeros(9)]
    checks = []
    for row in rows:
        observed = np.asarray(row['state_after_physics_11'][0])
        wrench = np.asarray(row['command']['telemetry']['applied_wrench_6'][0])
        prediction = predictor(prior[None], (wrench/np.r_[[context.mass]*3, context.inertia])[None], context)[0]
        checks.append(dict(step=len(checks)+1, observed_p=observed[8], predicted_p=prediction[8],
            angular_error=prediction[8:]-observed[8:], support_rejection=domain.check_states(observed[None])))
        prior = observed
    assert checks[-1]['support_rejection']['reason'] == 'state_out_of_support', 'original_symptom_not_reproduced'
    fit = []
    for episode in load_fit_cache(release):
        if episode.case['configuration'] != 'asymmetric': continue
        values = state_features(episode.states, control_mask('asymmetric'))
        fit.append(dict(case=episode.case, states_shape=episode.states.shape,
                        first_state=episode.states[0], max_p=float(values[:,7].max()),
                        max_p_index=int(values[:,7].argmax())))
    scenarios = {}
    refs = dict(pitch=np.array([5.5, np.cos(.02), 0., np.sin(.02), 0.]), neutral=np.array([5.5, 1., 0., 0., 0.]))
    for name in assets.domains:
        for task, reference in refs.items():
            scenarios[name+'-'+task] = simulate(assets, model, name, reference)
    scenarios['asymmetric-neutral-ideal-actuator'] = simulate(assets, model, 'asymmetric', refs['neutral'], ideal_actuator=True)
    for name in assets.domains:
        for task, reference in refs.items():
            scenarios[name+'-'+task+'-axiswise'] = simulate(assets, model, name, reference, axiswise=True)
    return dict(schema='offline-startup-diagnosis-v68', physical_experiments=0, new_fits=0,
        limitations=['model_rollout_is_not_Isaac', 'ideal_actuator_is_unphysical_counterfactual_only',
                      'offline_feedback_timeout_1000ms_not_online_qualification'],
        model_sha256=assets.model_sha256, original_failure_reproduced=True,
        teacher_forced_one_step=checks, asymmetric_fit=fit, scenarios=scenarios)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', type=Path, default=ROOT/'.pytest-tmp/phase9-runtime-v59-20260920')
    parser.add_argument('--trace', type=Path, default=ROOT/'docs/evidence/phase9/rate30-primary-v67-20260921/r3/results/asymmetric-pitch-feedback/output/diagnostic.json.gz')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.release, args.trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8') as stream: json.dump(result, stream, default=encode, allow_nan=False)
    print(json.dumps({name: {key: row.get(key) for key in ('steps', 'stop', 'peak_abs_roll_rate')}
        for name, row in result['scenarios'].items()}, default=encode))
