from __future__ import annotations

from typing import Any

from koopman_data import KoopmanDataLogger, build_koopman_sample


def _as_list(values: Any) -> list[float]:
    if hasattr(values, "detach"):
        values = values.detach().cpu().reshape(-1).tolist()
    elif hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, (int, float)):
        return [float(values)]
    result: list[float] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            result.extend(_as_list(value))
        else:
            result.append(float(value))
    return result


def state_vector_from_env(env: Any, env_index: int = 0) -> list[float]:
    data = env._robot.data
    return (
        _as_list(data.root_pos_w[env_index, 2])
        + _as_list(data.root_quat_w[env_index])
        + _as_list(data.root_lin_vel_b[env_index])
        + _as_list(data.root_ang_vel_b[env_index])
    )


def reference_vector(depth_ref: float, quat_ref: Any) -> list[float]:
    return [float(depth_ref)] + _as_list(quat_ref)


def record_koopman_step(
    logger: KoopmanDataLogger,
    *,
    t: float,
    env: Any,
    previous_state: list[float],
    reference: list[float],
    action_4d: Any,
    next_state: list[float],
    trajectory_type: str,
    controller_mode: str,
    solver_diagnostics: dict[str, Any] | None = None,
    env_index: int = 0,
) -> None:
    pwm_8d = getattr(env, "_last_pwm_8d", None)
    if pwm_8d is None:
        raise AttributeError("EasyUUVEnv must expose _last_pwm_8d before Koopman logging")

    sample = build_koopman_sample(
        t=t,
        state=previous_state,
        reference=reference,
        action_4d=action_4d,
        pwm_8d=pwm_8d[env_index],
        next_state=next_state,
        trajectory_type=trajectory_type,
        controller_mode=controller_mode,
    )
    if solver_diagnostics is not None:
        sample["solver_diagnostics"] = solver_diagnostics
    logger.write(sample)
