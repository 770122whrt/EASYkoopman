"""Bounded server supervisor. Source preparation/imports do not start Isaac."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from workflows.projected_resource_v38 import resource_limits
from workflows.projected_budget_v38 import reserve, settle, validate_budget, write_budget
from workflows.projected_protocol_v38 import cases, pulse, protocol
from workflows.projected_release_v38 import REMOTE_ROOT, TRANSFER_ROOT, read, sha, verify_collection_release


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')


def disk_bytes(root, transfer):
    total = 0
    for directory in (Path(root), Path(transfer)):
        for path in directory.rglob('*'):
            if path.is_symlink():
                raise ValueError('formal_disk_symlink')
            if path.is_file():
                total += path.stat().st_size
    return total


def check_disk(root, transfer):
    if disk_bytes(root, transfer) >= protocol()['resource_cap']['disk_bytes']:
        raise ValueError('formal_disk_budget')


def prepare(root, transfer, role):
    root, transfer = Path(root), Path(transfer)
    if str(root) != REMOTE_ROOT or str(transfer) != TRANSFER_ROOT:
        raise ValueError('formal_runtime_root')
    from workflows.collect_koopman_v21_identification import _repository_commit
    source = _repository_commit()
    verify_collection_release(root, transfer, source, role)
    if (transfer/role).exists():
        raise ValueError('formal_stage_already_attempted')
    budget = read(transfer/'budget.json')
    validate_budget(budget, sha(transfer/'freeze.json'))
    if any(row['status'] == 'reserved' for row in budget['attempts']):
        raise ValueError('formal_unsettled_budget')
    selected = cases(role)
    # Make the next catalog case reservable before creating the stage directory.
    remaining = 5400-budget['charged_seconds']['collector']
    if remaining < 30:
        raise ValueError('formal_collection_budget')
    reserve(budget, 'collector', selected[0]['run_id'], min(300., remaining))
    for q in selected:
        pulse(q)
    check_disk(root, transfer)
    return selected, source


def run(root, transfer, role):
    root, transfer = Path(root), Path(transfer)
    selected, source = prepare(root, transfer, role)
    directory = transfer/role
    directory.mkdir()
    status = dict(status='running', role=role, source_commit=source,
                  freeze_sha256=sha(transfer/'freeze.json'), accepted=[], rejected=[], trace_sha256={})
    budget_path = transfer/'budget.json'
    try:
        for q in selected:
            check_disk(root, transfer)
            budget = read(budget_path)
            remaining = 5400-budget['charged_seconds']['collector']
            if remaining < 30:
                raise ValueError('formal_collection_budget')
            seconds = min(300., remaining)
            budget = reserve(budget, 'collector', q['run_id'], seconds)
            write_budget(budget_path, budget)
            command = ['timeout', '--signal=TERM', '--kill-after=15s', f'{seconds-15}s',
                '/root/IsaacLab/isaaclab.sh', '-p', '-B', '-m', 'workflows.collect_projected_formal_v38',
                '--case', q['run_id'], '--output', str(directory/q['run_id']),
                '--source-commit', source, '--policy', str(transfer/'policy.json')]
            started, native_exit = time.monotonic(), 1
            try:
                with (directory/(q['run_id']+'.log')).open('x') as log:
                    native_exit = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT).returncode
            finally:
                budget = settle(budget, 'collector', q['run_id'], time.monotonic()-started, native_exit)
                write_budget(budget_path, budget)
                (directory/(q['run_id']+'.exit_status')).write_text(str(native_exit)+'\n')
            trace_path = directory/q['run_id']/'trace.json'
            if trace_path.is_file():
                status['trace_sha256'][q['run_id']] = sha(trace_path)
            if native_exit:
                status['rejected'].append(q['run_id'])
                raise ValueError('formal_native_failure_preserved')
            validate_budget(budget, status['freeze_sha256'])
            # Charge semantic checking to the separate new analysis budget.
            analysis_name = 'online_semantics:'+q['run_id']
            remaining = resource_limits(budget)['analysis_seconds']-budget['charged_seconds']['analysis']
            if remaining < 30:
                raise ValueError('formal_analysis_budget')
            budget = reserve(budget, 'analysis', analysis_name, remaining)
            write_budget(budget_path, budget)
            started, exit_code = time.monotonic(), 1
            try:
                from workflows.validate_projected_formal_v38 import validate_trace
                from workflows.projected_protocol_v38 import guarded_exit_code
                trace = read(trace_path)
                exits = read(directory/q['run_id']/'collector-exit.json')
                if (guarded_exit_code(exits.get('child_native_exit'), trace, q, source)
                        or exits.get('guarded_collector_exit') != 0 or exits.get('trace_sha256') != sha(trace_path)):
                    raise ValueError('formal_nested_native_failure')
                check = validate_trace(trace, q, source, root)
                if role == 'preflight' and not check['tail']['eligible_for_excitation']:
                    raise ValueError('formal_preflight_tail')
                dump(directory/(q['run_id']+'.validation.json'), check)
                exit_code = 0
            finally:
                budget = settle(budget, 'analysis', analysis_name, time.monotonic()-started, exit_code)
                write_budget(budget_path, budget)
            validate_budget(budget, status['freeze_sha256'])
            check_disk(root, transfer)
            status['accepted'].append(q['run_id'])
            dump(directory/'stage-status.json', status)
            print(json.dumps(dict(case=q['run_id'], status='semantic_checks_passed_pending_pullback')), flush=True)
        status['status'] = 'projected_formal_stage_completed_pending_pullback'
    except BaseException as exc:
        status.update(status='failed', exception=f'{type(exc).__name__}:{exc}')
        raise
    finally:
        dump(directory/'stage-status.json', status)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('preflight', 'validation', 'test'), required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.check_only:
        selected, source = prepare(root, TRANSFER_ROOT, args.stage)
        print(json.dumps(dict(status='prepared_only', source_commit=source, cases=len(selected))))
    else:
        run(root, TRANSFER_ROOT, args.stage)
