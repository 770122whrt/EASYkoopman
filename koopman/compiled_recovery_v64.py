"""Opt-in worker factories; retain frozen model loading and recovery checks."""
from koopman.bounded_mpc_v64 import BoundedMPC


def upgrade_solver(solver, *, share_prefix=False):
    old = solver.solver
    solver.solver = BoundedMPC(solver.domain, old.predictor,
        model_id=solver.domain.model_id, config=old.config, weights=old.weights,
        share_prefix=share_prefix)
    return solver


def portable_compiled_factory(spec):
    from workflows.runtime_assets_v56 import portable_model_factory
    return upgrade_solver(portable_model_factory(spec))


def portable_shared_factory(spec):
    from workflows.runtime_assets_v56 import portable_model_factory
    return upgrade_solver(portable_model_factory(spec), share_prefix=True)
