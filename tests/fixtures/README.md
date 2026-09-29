# Frozen behavior references

Both JSON files were generated from the historical implementation while the
repository HEAD was `7bbbbef`, before those modules were removed. They are
offline regression references, not simulator or performance measurements.

- `frozen_contract_7bbbbef.json`: complete v86/v87/v88 protocol records and all
  excitation-byte SHA-256 values; old v80 MPC bounds, symbolic outputs and exact
  checks for base/uuv4/uuv6; old v87 three-model forecasts and model identities;
  deterministic training-array hashes, metrics and frozen model record hash.
  Inputs are retained in the corresponding semantic tests and
  `control_fixtures.py`. Generation used the old classes throughout, avoiding
  mixing old and new context/domain types.
- `feedback_7bbbbef.json`: old feedback-map evaluations, repeated cache use,
  nine state/reference/previous-command combinations per configuration,
  startup preparation and audit results for base/uuv4/uuv6. Only measured
  durations (`elapsed_ms`, `prepare_ms`) were omitted.

Tests also execute current IPOPT optimization and timeout handling, current
spawned-worker lifecycle, causal forecast branches and full lifted-state
propagation. These checks complement the frozen references. Do not regenerate
the expected JSON from changed current code merely to make a regression pass.
