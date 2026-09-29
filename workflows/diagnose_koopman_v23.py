"""One frozen source-only case. Run with python -m workflows.diagnose_koopman_v23.

No grid search, test trajectories, selection, model export or canonical writes.
The 1/5/20/60 probes all start at zero; they are NOT official sliding metrics.
The full probe exactly matches the official full-horizon failure gate.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.diagnostics_v23 import SourceOnlyReader, diagnose_window, json_safe, reserve_output
from koopman.evaluation_v21 import DatasetFormalLocoBackendV21, load_protocol_episode_registry_v21
from koopman.loco_v21 import CandidateSpecV21
from koopman.metrics_v21 import OFFICIAL_ROLLOUT_POLICY_V21, RolloutEpisodeV21
from koopman.platform_features_v21 import fit_source_pca_v21

CASE_ID = '4c66d783f92795e479ccf427601e0fed61573d263cdedb294f42d13271d67d42'
SOURCE_COMMIT = '4f3b4cbeb3a76b0ae82ce57d8c444f33795d2162'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = repo / 'tmp' / 'phase8_3'
    if not root.resolve().is_relative_to(repo / 'tmp'):
        raise ValueError('diagnostic_output_escape')
    output = reserve_output(root, args.run_id)
    dataset_root = repo / 'source/results/koopman_phase8_2/dataset'
    role = repo / 'protocols/phase8_1/main_role_assignment_protocol.json'
    analysis = repo / 'protocols/phase8_1/analysis_policy.json'
    for path, expected in ((role, '083d5eae3729e9939287345ab258dbfe4b4c8ca71ab769c2fd8616431a649417'),
                           (analysis, '7a790b43d0f1581b8995ccdcbd9b6d259cb09bc8fe2268201400243d05f1e18c')):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('frozen_protocol_hash_mismatch')
    registry = load_protocol_episode_registry_v21(
        role_protocol_path=role, inventory_path=dataset_root / 'dataset_inventory.json')
    sources = tuple(c for c in SUPPORTED_EMBODIMENTS if c != 'base')
    bindings = tuple(b for c in sources for b in (
        *registry.for_configuration_role(c, 'fit')[:2],
        *registry.for_configuration_role(c, 'validation')))
    candidate = CandidateSpecV21(
        family='conditional', observable_schema='so3_identity_v1', data_prefix=2,
        ridge=1e-8, normalization='none', conditioning='structured_pca2',
        label='conditional:so3_identity_v1:p2:r1e-08:none')
    if candidate.candidate_id != CASE_ID:
        raise ValueError('frozen_candidate_mismatch')
    backend = DatasetFormalLocoBackendV21(
        dataset_root=dataset_root, analysis_policy_path=analysis,
        expected_source_commit=SOURCE_COMMIT, expected_evidence_level='server_isaac_smoke')
    reader = SourceOnlyReader(backend, bindings)
    report = {'schema': 'phase8.3-local-forensics-v1', 'candidate_id': CASE_ID,
              'heldout': 'base', 'source_configurations': sources,
              'evidence_level': 'local_replay_of_archived_source_data',
              'source_commit': SOURCE_COMMIT, 'opens': [], 'episodes': [],
              'read_test_trajectories': False, 'read_heldout_trajectories': False,
              'policy_sha256': OFFICIAL_ROLLOUT_POLICY_V21.policy_sha256,
              'probe_scope': 'start=0 for 1/5/20/60/full; full matches official full gate',
              'runtime_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
              'code_sha256': {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (Path(__file__), repo / 'koopman/diagnostics_v23.py',
                                       repo / 'koopman/model_v21.py', repo / 'koopman/metrics_v21.py',
                                       repo / 'koopman/evaluation_v21.py')}}
    def save():
        (output / 'report.json').write_text(json.dumps(json_safe(report), ensure_ascii=False,
                                          indent=2, allow_nan=False) + '\n', encoding='utf-8')
    # Publish the role/path allowlist before the first dataset open.
    report['allowlist'] = [b.to_dict() for b in bindings]
    save()
    try:
        loaded = []
        for binding in bindings:
            data = reader.open_episode(binding)
            loaded.append((binding, data))
            report['opens'].append(binding.to_dict())
            save()
            print(f'loaded {len(loaded)}/35 {binding.episode_id}', flush=True)
        descriptors = {c: backend._descriptor(next(d for b, d in loaded if b.configuration == c))
                       for c in sources}
        projector = fit_source_pca_v21(descriptors, source_configurations=sources)
        model = backend._fit_model(candidate, loaded, sources, projector)
        report['numerics'] = dict(model.diagnostics)
        report['model_sha256'] = model.model_sha256
        report['pca_sha256'] = projector.projector_sha256
        save()
        for binding, data in loaded:
            if binding.role != 'validation':
                continue
            episode = RolloutEpisodeV21.from_dataset(data)
            score = projector.transform(backend._descriptor(data))
            probes = {str(length): diagnose_window(model, episode, start=0, steps=length,
                                                   platform_score=score)
                      for length in (1, 5, 20, 60, episode.transition_count)}
            report['episodes'].append({'episode_id': binding.episode_id, 'probes': probes})
            save()
            full = probes[str(episode.transition_count)]
            print(f"{binding.episode_id}: {full['reason_code']} at {full['failure_transition_index']}", flush=True)
        report['status'] = 'completed_local_diagnostic'
    except Exception as exc:
        report['status'] = 'failed_local_diagnostic'
        report['exception'] = f'{type(exc).__name__}: {exc}'
        save()
        raise
    save()
    print(output / 'report.json', flush=True)


if __name__ == '__main__':
    main()
