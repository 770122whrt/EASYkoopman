from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.dataset import load_dataset
from koopman.edmd import fit_edmd
from koopman.lifting import LiftingConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train an offline EasyUUV Koopman/EDMD model from JSONL logs.")
    parser.add_argument("logs", nargs="+", type=Path, help="Koopman JSONL log paths.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "source" / "results" / "koopman_models" / "koopman_model.json",
        help="Output model artifact path.",
    )
    parser.add_argument("--ridge", type=float, default=1e-6, help="Ridge regularization coefficient.")
    parser.add_argument("--quadratic", action="store_true", help="Include elementwise quadratic lifting terms.")
    args = parser.parse_args(argv)

    dataset = load_dataset(args.logs)
    model = fit_edmd(
        dataset,
        lifting_config=LiftingConfig(include_quadratic=args.quadratic),
        ridge=args.ridge,
    )
    model.save(args.output)
    print(f"[INFO] trained Koopman model on {dataset.sample_count} samples")
    print(f"[INFO] wrote model artifact to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

