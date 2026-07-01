from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.sweep import run_sweep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep EasyUUV Koopman candidates and baselines.")
    parser.add_argument("--split-manifest", required=True, type=Path, help="Train/validation/test split JSON.")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for sweep models, metrics, normalizers and summary.",
    )
    parser.add_argument(
        "--ridge",
        action="append",
        type=float,
        default=None,
        help="Ridge value. Repeat to override the default sweep.",
    )
    parser.add_argument(
        "--lifting-variant",
        action="append",
        choices=("linear", "selected_quadratic"),
        default=None,
        help="Lifting variant. Repeat to override defaults.",
    )
    parser.add_argument(
        "--normalization",
        action="append",
        choices=("off", "standard"),
        default=None,
        help="Normalization mode. Repeat to override defaults.",
    )
    args = parser.parse_args(argv)

    summary = run_sweep(
        args.split_manifest,
        args.output_dir,
        ridge_values=tuple(args.ridge) if args.ridge else (1e-8, 1e-6, 1e-4, 1e-2),
        lifting_variants=tuple(args.lifting_variant) if args.lifting_variant else ("linear", "selected_quadratic"),
        normalization_modes=tuple(args.normalization) if args.normalization else ("off", "standard"),
    )
    print(f"[INFO] wrote sweep results to {args.output_dir / 'sweep_results.json'}")
    print(f"[INFO] best candidate: {summary.get('best_candidate_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
