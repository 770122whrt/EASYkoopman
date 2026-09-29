from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


REFINEMENT_BY_PROFILE = {
    "rm_timeout16": ["rm_timeout15"],
    "rm_midweights_timeout14": ["rm_interpolate_weights_timeout14"],
    "rm_lightweights_timeout14": ["rm_interpolate_weights_timeout14"],
    "r_pwm035": ["r_pwm0325"],
}


def plan_phase54_refinement_profiles(selection: dict[str, Any]) -> dict[str, Any]:
    selected_score = selection.get("selected_score") or {}
    selected_profile_id = selection.get("selected_profile_id") or selection.get("best_non_promoted_profile_id")
    if not selected_profile_id:
        selected_profile_id = selected_score.get("profile_id")

    if selection.get("selection_status") == "no_selection":
        return {
            "refinement_required": False,
            "diagnostic_stop_allowed": True,
            "nearest_smaller_candidate_required": False,
            "recommended_profile_ids": [],
            "reason": "No Round 1 profile was promotable.",
        }

    recommended = REFINEMENT_BY_PROFILE.get(str(selected_profile_id), [])
    if not recommended and selected_score.get("track") == "RM":
        recommended = ["rm_timeout15"]
    if not recommended and selected_score.get("track") == "R":
        recommended = ["r_pwm0325"]

    return {
        "refinement_required": True,
        "diagnostic_stop_allowed": False,
        "nearest_smaller_candidate_required": True,
        "source_profile_id": selected_profile_id,
        "recommended_profile_ids": recommended,
        "probed_bottlenecks": selected_score.get("remaining_bottlenecks", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan Phase 5.4 Round 2 refinement profiles.")
    parser.add_argument("--selection_path", required=True, type=Path)
    parser.add_argument("--output_path", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        selection = json.loads(args.selection_path.read_text(encoding="utf-8-sig"))
        plan = plan_phase54_refinement_profiles(selection)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(plan, indent=2)
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
