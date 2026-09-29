from workflows.select_phase5_3_candidate import recommend_next_tuning_axis


def test_reward_adapter_cross_routes_to_adapter_and_saturation_penalty_sweep():
    handoff = recommend_next_tuning_axis("cross_reward_v1_adapter_soft")

    assert handoff["next_tuning_axis"] == "adapter_scale_and_saturation_reward_sweep"
    assert "adapter_rpy_delta_scale" in handoff["parameters_to_sweep_next"]
    assert "phase5_2_w_pwm_sat" in handoff["parameters_to_sweep_next"]
    assert handoff["final_policy_claim_allowed"] is False


def test_mpc_cross_routes_to_cautious_mpc_weight_sweep():
    handoff = recommend_next_tuning_axis("cross_reward_v1_mpc_health")

    assert handoff["next_tuning_axis"] == "mpc_weight_sweep_with_clip_guard"
    assert "mpc_control_weight" in handoff["parameters_to_sweep_next"]
    assert "mpc_smoothness_weight" in handoff["parameters_to_sweep_next"]
    assert handoff["final_policy_claim_allowed"] is False
