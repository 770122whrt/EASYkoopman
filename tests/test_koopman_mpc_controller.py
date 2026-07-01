import numpy as np

from koopman.mpc import MPCBounds, MPCConfig
from koopman.mpc_controller import KoopmanMPCController


class Runtime:
    backend_used = "direct_state"
    model_class = "direct_state"
    backend_is_paper_style_lifted_edmd = False
    known_limitations = ("fixture limitation",)

    def predict_next(self, state, pwm, reference):
        next_state = np.asarray(state, dtype=float).copy()
        next_state[0] += 0.5 * float(np.asarray(pwm)[0])
        return next_state


def test_controller_returns_bounded_pwm_and_solver_diagnostics():
    state = np.zeros(11)
    state[0] = 1.0
    state[1] = 1.0
    reference = np.zeros(5)
    reference[1] = 1.0

    controller = KoopmanMPCController(
        Runtime(),
        MPCConfig(horizon=3, bounds=MPCBounds(delta_pwm_limit=1.0), timeout_ms=50),
    )
    output = controller.command(
        state,
        reference,
        previous_pwm=np.zeros(8),
        legacy_pwm=np.full(8, 0.2),
    )

    assert output.pwm.shape == (8,)
    assert np.all(output.pwm >= -1.0)
    assert np.all(output.pwm <= 1.0)
    assert output.diagnostics["backend_used"] == "direct_state"
    assert "latency_ms" in output.diagnostics
    assert "fallback_used" in output.diagnostics


def test_controller_falls_back_to_legacy_on_nonfinite_state():
    controller = KoopmanMPCController(Runtime(), MPCConfig(horizon=2))
    state = np.zeros(11)
    state[0] = float("nan")
    reference = np.zeros(5)
    legacy_pwm = np.full(8, -0.25)

    output = controller.command(state, reference, previous_pwm=np.zeros(8), legacy_pwm=legacy_pwm)

    assert output.fallback_used is True
    assert output.diagnostics["fallback_reason"] == "nonfinite_input"
    np.testing.assert_allclose(output.pwm, legacy_pwm)


def test_easyuuv_and_play_controller_source_contracts_for_koopman_mpc():
    env_source = open("easyuuv_env.py", encoding="utf-8").read()
    play_source = open("workflows/play_controller.py", encoding="utf-8").read()

    assert "koopman_manifest_path" in env_source
    assert "mpc_horizon" in env_source
    assert "KoopmanMPCController" in env_source
    assert "NotImplementedError" not in env_source
    assert "self._last_pwm_8d = motorValues.clone()" in env_source
    assert "controller_mode == 'legacy'" in env_source
    assert "controller_mode == 'koopman_mpc'" in env_source

    assert "--controller_mode" in play_source
    assert "--koopman_manifest_path" in play_source
    assert "--mpc_horizon" in play_source
    assert "--mpc_timeout_ms" in play_source
    assert "_koopman_reference_5d" in play_source
