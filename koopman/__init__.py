"""EasyUUV prediction and control, without eager historical model imports.

Current control entrypoints are ``continuous_mpc`` and ``control_solver``.
The former public exports remain lazy for historical callers pending cleanup.
"""
from importlib import import_module

_EXPORTS = {
    "KoopmanDataset": "dataset", "load_dataset": "dataset",
    "fit_edmd": "edmd", "LiftingConfig": "lifting",
    "lift_state_reference": "lifting", "LiftedEDMDModel": "lifted_edmd",
    "fit_lifted_edmd": "lifted_edmd", "MPCBounds": "mpc",
    "MPCConfig": "mpc", "MPCResult": "mpc", "MPCWeights": "mpc",
    "solve_mpc": "mpc", "KoopmanMPCController": "mpc_controller",
    "KoopmanModel": "model", "KoopmanRuntime": "runtime",
    "load_koopman_runtime": "runtime",
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{_EXPORTS[name]}", __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "KoopmanDataset",
    "KoopmanModel",
    "LiftingConfig",
    "LiftedEDMDModel",
    "MPCBounds",
    "MPCConfig",
    "MPCResult",
    "MPCWeights",
    "KoopmanMPCController",
    "KoopmanRuntime",
    "fit_edmd",
    "fit_lifted_edmd",
    "lift_state_reference",
    "load_koopman_runtime",
    "load_dataset",
    "solve_mpc",
]
