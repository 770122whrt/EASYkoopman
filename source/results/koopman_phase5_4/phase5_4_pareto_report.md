# Phase 5.4 Pareto Report

Final status: `no_selection`

No Phase 5.4 profile passed the Pareto gates. All 11 Round 1 profiles completed 200-iteration PPO training and matched `step/sine/irregular` evaluation.

Key finding: latency is healthy, but reward/MPC-only tuning trades one protected strength for another. Track R loses `reward_v1_only` fallback. Track RM either loses MPC-health clip/depth/attitude strengths or shifts fallback into `no_cost_improvement`.

Primary artifacts:

- `phase5_4_final_selection.json`
- `phase5_4_round1_selection.json`
- `phase5_4_round2_plan.json`
- `selected_phase5_4_profile_manifest.json`
- `<profile>/candidate_summary.json`
- `<profile>/candidate_matched_metrics.json`

Recommended next phase: adapter/reference-action diagnosis plus fallback-reason-aware MPC diagnostics.
