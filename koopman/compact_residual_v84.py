"""Source-fixed, physically structured velocity residual for the v84 comparison.

The 53-feature storage format is retained for exact prepared/symbolic parity,
but only 15 tied coefficient directions (27 matrix entries) may change. Body
axis drag transforms consistently into world velocity; angular corrections
stay on the corresponding axis. Known buoyancy, gyro, input and pose maps
remain physical. This is projected nonlinear prediction, not full-lift closure.

RMS scaling without centering/free intercept avoids the constant-column noise
and duplicate velocity directions in R53. It changes the regularizer as well
as the model space: this arm is NOT an equivalent rewrite of the old fit.
Structural constraints alone do not guarantee passivity or rollout stability.
"""
import copy
from dataclasses import dataclass, replace
import hashlib
import json

import numpy as np

from koopman.prepared_projected_v40 import prepare_projected, _immutable
from koopman.sparse_world_edmd_v30 import feature_names
from workflows.identify_sparse_world_v30 import from_record


SCHEMA = 'compact-projected-velocity-residual-v84'
STRUCTURE = 'tied-body-drag-same-axis-restoring-v1'
EXCITATION_RMS_MIN = 1e-8


def structural_basis():
    """Fixed 15 x 53 x 6 basis; never selected from held-out errors."""
    index = {name: i for i, name in enumerate(feature_names('nonlinear'))}
    matrices, names = [], []
    for group in ('axis_velocity', 'axis_quadratic'):
        for axis in range(3):
            b = np.zeros((53, 6))
            for output in range(3):
                b[index[f'{group}_{axis}_{output}'], output] = 1.
            matrices.append(b)
            names.append(f'tied_{group}_{axis}')
    for group in ('wb', 'angular_quadratic_', 'restoring_body_'):
        for axis in range(3):
            b = np.zeros((53, 6))
            b[index[f'{group}{axis}'], 3 + axis] = 1.
            matrices.append(b)
            names.append(f'same_axis_{group}{axis}')
    return np.stack(matrices), names


def structural_mask():
    return np.any(structural_basis()[0] != 0, axis=0)


def fit_compact(features, target, weights, physical_prior_matrix, ridge=.001):
    """Fit only supplied source rows; target excludes the known input term.

Minimize E_w ||target - features @ (prior + sum theta_j basis_j)||^2
plus ridge * sum_j (source_RMS_j * theta_j)^2. Directions whose
source RMS is below 1e-8 retain theta=0. No fitted intercept is introduced.
"""
    a, y = np.asarray(features, float), np.asarray(target, float)
    w, prior = np.asarray(weights, float), np.asarray(physical_prior_matrix, float)
    if (a.ndim != 2 or a.shape[1] != 53 or len(a) < 2
            or y.shape != (len(a), 6) or w.shape != (len(a),)
            or prior.shape != (53, 6) or ridge not in (.001, .1)
            or np.any(w <= 0) or not all(np.isfinite(v).all() for v in (a, y, w, prior))
            or not np.all(a[:, -1] == 1)):
        raise ValueError('compact_fit_input')
    wn = (w / np.max(w)) / np.sum(w / np.max(w))
    basis, names = structural_basis()
    design = np.einsum('nf,jfo->noj', a, basis)
    rms = np.sqrt(np.einsum('n,noj,noj->j', wn, design, design))
    active = rms >= EXCITATION_RMS_MIN
    coefficient = np.zeros(len(basis))
    residual = y - a @ prior
    rank = 0
    if active.any():
        scaled = design[:, :, active] / rms[active]
        z = scaled.reshape(-1, int(active.sum()))
        repeated_w = np.repeat(wn, 6)
        normal = z.T @ (repeated_w[:, None] * z) + ridge * np.eye(z.shape[1])
        rhs = z.T @ (repeated_w * residual.ravel())
        coefficient[active] = np.linalg.solve(normal, rhs) / rms[active]
        rank = int(np.linalg.matrix_rank(z * np.sqrt(repeated_w[:, None])))
    increment = np.einsum('j,jfo->fo', coefficient, basis)
    fitted = prior + increment
    return fitted, {
        'structure': STRUCTURE,
        'regularizer': 'source_rms_no_center_no_intercept_tied_basis',
        'basis_names': names,
        'basis_coefficients': coefficient.tolist(),
        'basis_rms': rms.tolist(),
        'identified_basis_indices': np.flatnonzero(active).tolist(),
        'fixed_prior_basis_indices': np.flatnonzero(~active).tolist(),
        'excitation_rms_min': EXCITATION_RMS_MIN,
        'independent_coefficients': len(basis),
        'allowed_matrix_entries': int(structural_mask().sum()),
        'design_rank': rank,
        'rows': len(a),
        'weighted_rows': float(w.sum()),
        'weighted_velocity_rmse': np.sqrt(wn @ ((a @ fitted - y) ** 2)).tolist(),
        'physical_prior_weighted_velocity_rmse': np.sqrt(wn @ (residual ** 2)).tolist(),
        'learned_increment_frobenius': float(np.linalg.norm(increment)),
    }


def seal_record(record):
    result = copy.deepcopy(record)
    result.pop('content_sha256', None)
    result['content_sha256'] = hashlib.sha256(json.dumps(
        result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return result


def make_record(physical_prior, fitted, stats, *, ridge, extra_audit=None):
    """Bind fit inventory/mechanics to the matrix; optional audit adds provenance.

The caller should add feature/target/weight hashes and fold identity to
extra_audit. Those cannot be inferred from a matrix or asserted here.
"""
    audit = dict(extra_audit or {})
    audit.update(training_role='fit', fit_episodes=len(physical_prior['fit_episode_hashes']),
                 startup_weight=1/3, analytic_pose=True, full_latent_closure_claim=False)
    record = seal_record(dict(
        schema=SCHEMA, family='nonlinear', structure=STRUCTURE,
        feature_names=feature_names('nonlinear'), ridge=ridge,
        physical_prior=physical_prior, velocity_matrix=np.asarray(fitted, float).tolist(),
        fit_statistics=stats, audit=audit))
    validate_record(record)
    return record


def validate_record(record, *, expected_sha256=None):
    try:
        if (record.get('content_sha256') != seal_record(record)['content_sha256']
                or expected_sha256 is not None and record['content_sha256'] != expected_sha256):
            raise ValueError('compact_hash')
        audit = record['audit']
        if (record['schema'] != SCHEMA or record['family'] != 'nonlinear'
                or record['structure'] != STRUCTURE
                or record['feature_names'] != feature_names('nonlinear')
                or record['ridge'] not in (.001, .1) or audit['training_role'] != 'fit'
                or audit['analytic_pose'] is not True or audit['full_latent_closure_claim'] is not False
                or audit['startup_weight'] != 1/3
                or audit['fit_episodes'] != len(record['physical_prior']['fit_episode_hashes'])):
            raise ValueError('compact_record')
        prior = from_record(record['physical_prior'])
        if prior.family != 'nonlinear':
            raise ValueError('compact_prior_family')
        k = np.asarray(record['velocity_matrix'], float)
        if k.shape != (53, 6) or not np.isfinite(k).all():
            raise ValueError('compact_matrix')
        delta = k - prior.matrix[:, 10:16]
        basis, names = structural_basis()
        if np.any(delta[~structural_mask()] != 0):
            raise ValueError('compact_forbidden_coefficient')
        for b in basis:
            values = delta[b != 0]
            if not np.allclose(values, values[0], rtol=0, atol=1e-13):
                raise ValueError('compact_untied_coefficient')
        stats = record['fit_statistics']
        rms = np.asarray(stats['basis_rms'], float)
        if (stats['structure'] != STRUCTURE or stats['basis_names'] != names
                or rms.shape != (15,) or not np.isfinite(rms).all() or np.any(rms < 0)
                or stats['independent_coefficients'] != 15 or stats['allowed_matrix_entries'] != 27):
            raise ValueError('compact_statistics')
        return prior, k
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('compact_record') from exc


@dataclass(frozen=True)
class CompactResidual:
    _symbolic_base: object
    content_sha256: str
    model_kind: str = 'compact_projected_residual_v84'

    def __call__(self, states, acceleration, context):
        return self._symbolic_base(states, acceleration, context)


def prepare_compact(record, context, *, expected_sha256=None):
    prior, k = validate_record(record, expected_sha256=expected_sha256)
    base = prepare_projected(prior, context)
    matrix = base._matrix.copy()
    matrix[:, 10:16] = k
    return CompactResidual(replace(base, _matrix=_immutable(matrix)), record['content_sha256'])
