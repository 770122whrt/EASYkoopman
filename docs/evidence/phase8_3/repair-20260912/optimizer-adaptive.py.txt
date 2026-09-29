"""Exploratory stability-constrained refit; not a formal model/handoff format."""

import numpy as np

UNBOUNDED_FEATURE_COLUMNS = (1, 8, 9, 10, 11, 12, 13)


def context_maps(scores, scales):
    """M_s such that D^-1 C M_s + I is the scaled seven-state recurrence."""
    maps = []
    for score in scores:
        mapping = np.zeros((66, 7))
        for j, column in enumerate(UNBOUNDED_FEATURE_COLUMNS):
            mapping[column, j] = scales[j]
            mapping[24 + column - 1, j] = score[0] * scales[j]
            mapping[45 + column - 1, j] = score[1] * scales[j]
        maps.append(mapping)
    return np.asarray(maps)


def constrained_refit(design, targets, baseline_coefficient, scores, scales, *,
                      ridge, radius=.999, max_iterations=5000):
    """Solve a convex, fixed-context contraction-constrained ridge problem.

    Only the first seven increment outputs (z,v,omega) are refit. Orientation
    increments remain unchanged. Objective is ridge on output errors scaled by
    source-fit state standard deviations. Unconstrained row-wise optima equal
    ordinary ridge; the new contraction constraints couple those rows.

    ADMM projects seven small matrices onto the spectral-norm ball. Returned
    coefficients must pass independent primal/dual and norm checks. This is a
    conservative diagnostic prior, not a guarantee of physical/model accuracy.
    """
    x, y, original, scores, scales = [np.asarray(v, dtype=float) for v in
                                     (design, targets, baseline_coefficient, scores, scales)]
    if (x.ndim != 2 or x.shape[1] != 66 or y.shape != (len(x), 10)
            or original.shape != (10, 66) or scores.shape != (7, 2) or scales.shape != (7,)
            or any(not np.isfinite(v).all() for v in (x, y, original, scores, scales))
            or np.any(scales <= 0) or not 0 < radius < 1 or not np.isfinite(ridge) or ridge <= 0
            or isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1):
        raise ValueError('stability_refit_invalid')
    maps = context_maps(scores, scales)
    gram = x.T @ x + ridge * np.eye(66)
    rhs = (y[:, :7] / scales).T @ x
    penalty_gram = sum(m @ m.T for m in maps)
    beta = float(np.trace(gram) / max(np.trace(penalty_gram), 1e-12))
    system = gram + beta * penalty_gram
    # Fixed system: solve once, reuse the inverse action during the bounded loop.
    inverse = np.linalg.solve(system, np.eye(66))
    coefficient = original[:7].copy() / scales[:, None]
    identity = np.eye(7)
    def project(matrix):
        u, singular, vt = np.linalg.svd(matrix, full_matrices=False)
        return (u * np.minimum(singular, radius)) @ vt
    z = np.asarray([project(identity + coefficient @ m) for m in maps])
    dual = np.zeros_like(z)
    converged = False
    penalty_updates = 0
    rhs_norm = max(float(np.linalg.norm(rhs)), 1.)
    for iteration in range(1, max_iterations + 1):
        constrained_rhs = sum((zs - identity - us) @ m.T for zs, us, m in zip(z, dual, maps))
        coefficient = (rhs + beta * constrained_rhs) @ inverse
        a = np.asarray([identity + coefficient @ m for m in maps])
        previous_z = z.copy()
        z = np.asarray([project(value + us) for value, us in zip(a, dual)])
        dual += a - z
        primal = float(np.max(np.linalg.norm(a - z, axis=(1, 2))))
        dual_residual = float(beta * np.linalg.norm(sum((zs - prev) @ m.T
                                       for zs, prev, m in zip(z, previous_z, maps))) / rhs_norm)
        if primal <= 1e-7 and dual_residual <= 1e-7:
            converged = True
            break
        # Balance residuals measured relative to their fixed stopping tolerances.
        # This changes the numerical penalty, not the objective or feasible set.
        if iteration % 25 == 0:
            new_beta = beta
            if primal > 10 * dual_residual:
                new_beta = min(beta * 2, 1e12)
            elif dual_residual > 10 * primal:
                new_beta = max(beta / 2, 1e-12)
            if new_beta != beta:
                dual *= beta / new_beta
                beta = new_beta
                inverse = np.linalg.solve(gram + beta * penalty_gram, np.eye(66))
                penalty_updates += 1
    norms = [float(np.linalg.norm(identity + coefficient @ m, 2)) for m in maps]
    if not converged or max(norms) > radius + 1e-6:
        raise ValueError(f'stability_refit_not_converged:iterations={iteration}:primal={primal}:dual={dual_residual}:norm={max(norms)}')
    result = original.copy()
    result[:7] = coefficient * scales[:, None]
    return result, {'converged': True, 'iterations': iteration, 'primal_residual': primal,
                    'relative_dual_residual': dual_residual, 'radius': radius, 'beta': beta,
                    'penalty_updates': penalty_updates,
                    'scaled_operator_norms': norms, 'scales_from_fit': scales.tolist(),
                    'guarantee_scope': 'seven fixed source contexts; bounded inputs and rotation features; not prediction accuracy or closed-loop safety'}


class DiagnosticCoefficientModel:
    """Runtime-neutral prediction adapter, deliberately lacking model promotion APIs."""
    def __init__(self, coefficient):
        value = np.array(coefficient, dtype=float, copy=True)
        if value.shape != (10, 66) or not np.isfinite(value).all():
            raise ValueError('diagnostic_coefficient_invalid')
        value.setflags(write=False)
        self.coefficient = value

    def predict_increment(self, state, memory, control, *, platform_score=None):
        from koopman.model_v21 import build_observable_features_v21, build_conditional_design_v21
        phi = build_observable_features_v21(state, memory, control, 'so3_identity_v1')
        design = build_conditional_design_v21(phi, platform_score)
        return design @ self.coefficient.T
