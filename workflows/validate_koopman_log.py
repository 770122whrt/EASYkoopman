from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman_data import load_koopman_samples, summarize_koopman_samples


def _join_values(values: list[str]) -> str:
    return ",".join(values) if values else "none"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize an EasyUUV Koopman JSONL log.")
    parser.add_argument("path", type=Path, help="Path to a Koopman JSONL log.")
    args = parser.parse_args(argv)

    try:
        samples = load_koopman_samples(args.path)
        summary = summarize_koopman_samples(samples)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"OK: {summary['count']} samples")
    print(
        " ".join(
            [
                f"state_dim={summary['state_dim']}",
                f"reference_dim={summary['reference_dim']}",
                f"action_dim={summary['action_dim']}",
                f"pwm_dim={summary['pwm_dim']}",
            ]
        )
    )
    print(f"t_start={summary['t_start']:.9f} t_end={summary['t_end']:.9f}")
    print(f"trajectory_types={_join_values(summary['trajectory_types'])}")
    print(f"controller_modes={_join_values(summary['controller_modes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
