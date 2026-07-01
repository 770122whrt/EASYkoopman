from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM

from .lifted_edmd import LiftedEDMDModel
from .model import KoopmanModel


SUPPORTED_MODEL_CLASSES = {"direct_state", "paper_lifted_edmd"}


class KoopmanRuntimeError(ValueError):
    """Raised when a Phase 2.5 model manifest is unsafe for runtime use."""


@dataclass(frozen=True)
class KoopmanRuntime:
    manifest_path: Path | None
    manifest: dict[str, Any]
    model: Any
    model_path: Path
    backend_used: str
    model_class: str
    dt: float
    known_limitations: tuple[str, ...]

    @property
    def backend_is_paper_style_lifted_edmd(self) -> bool:
        return self.model_class == "paper_lifted_edmd"

    def predict_next(self, state: np.ndarray, pwm: np.ndarray, reference: np.ndarray) -> np.ndarray:
        prediction = np.asarray(self.model.predict_next(state, pwm, reference), dtype=float)
        if prediction.shape != (STATE_DIM,):
            raise KoopmanRuntimeError(f"predict_next returned shape {prediction.shape}, expected ({STATE_DIM},)")
        if not np.isfinite(prediction).all():
            raise KoopmanRuntimeError("predict_next returned non-finite values")
        return prediction


def _resolve_path(path_value: str | Path | None, *, base_path: Path | None, project_root: Path) -> Path:
    if not path_value:
        raise KoopmanRuntimeError("model_path is required")
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate

    cwd_candidate = project_root / candidate
    if cwd_candidate.exists():
        return cwd_candidate

    if base_path is not None:
        base_candidate = base_path.parent / candidate
        if base_candidate.exists():
            return base_candidate

    return cwd_candidate


def _require_int(manifest: dict[str, Any], field: str, expected: int) -> None:
    actual = manifest.get(field)
    if int(actual) != expected:
        raise KoopmanRuntimeError(f"{field} must be {expected}, got {actual}")


def _load_model(model_class: str, model_path: Path) -> Any:
    if model_class == "direct_state":
        return KoopmanModel.load(model_path)
    if model_class == "paper_lifted_edmd":
        return LiftedEDMDModel.load(model_path)
    raise KoopmanRuntimeError(f"Unsupported model_class: {model_class}")


def load_koopman_runtime_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: str | Path | None = None,
    project_root: str | Path | None = None,
) -> KoopmanRuntime:
    if manifest.get("gate_status") != "pass":
        raise KoopmanRuntimeError(f"gate_status must be 'pass', got {manifest.get('gate_status')!r}")

    model_class = str(manifest.get("model_class", ""))
    if model_class not in SUPPORTED_MODEL_CLASSES:
        raise KoopmanRuntimeError(f"Unsupported model_class: {model_class}")

    _require_int(manifest, "state_dim", STATE_DIM)
    _require_int(manifest, "reference_dim", REFERENCE_DIM)
    _require_int(manifest, "control_dim", PWM_DIM)

    dt = float(manifest.get("dt", 0.0))
    if not np.isfinite(dt) or dt <= 0.0:
        raise KoopmanRuntimeError(f"dt must be positive and finite, got {manifest.get('dt')!r}")

    resolved_manifest_path = Path(manifest_path) if manifest_path is not None else None
    root = Path(project_root) if project_root is not None else Path.cwd()
    model_path = _resolve_path(manifest.get("model_path"), base_path=resolved_manifest_path, project_root=root)
    if not model_path.exists():
        raise KoopmanRuntimeError(f"model_path does not exist: {model_path}")

    model = _load_model(model_class, model_path)
    if int(getattr(model, "state_dim", -1)) != STATE_DIM:
        raise KoopmanRuntimeError("loaded model state_dim does not match runtime contract")
    if int(getattr(model, "reference_dim", -1)) != REFERENCE_DIM:
        raise KoopmanRuntimeError("loaded model reference_dim does not match runtime contract")
    if int(getattr(model, "control_dim", -1)) != PWM_DIM:
        raise KoopmanRuntimeError("loaded model control_dim does not match runtime contract")

    limitations = tuple(str(item) for item in manifest.get("known_limitations", []) if str(item).strip())
    return KoopmanRuntime(
        manifest_path=resolved_manifest_path,
        manifest=dict(manifest),
        model=model,
        model_path=model_path,
        backend_used=model_class,
        model_class=model_class,
        dt=dt,
        known_limitations=limitations,
    )


def load_koopman_runtime(
    manifest_path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> KoopmanRuntime:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return load_koopman_runtime_from_manifest(manifest, manifest_path=path, project_root=project_root)
