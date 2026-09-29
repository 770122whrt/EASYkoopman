from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.dataset import load_dataset
from koopman.evaluation import evaluate_model, write_metrics
from koopman.model import KoopmanModel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate an offline EasyUUV Koopman model on JSONL logs.")
    parser.add_argument("--model", required=True, type=Path, help="Saved Koopman model JSON path.")
    parser.add_argument("--logs", nargs="+", required=True, type=Path, help="Koopman JSONL log paths.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "source" / "results" / "koopman_models" / "koopman_metrics.json",
        help="Output metrics JSON path.",
    )
    parser.add_argument("--horizon", type=int, default=20, help="Maximum multi-step rollout horizon.")
    args = parser.parse_args(argv)

    model = KoopmanModel.load(args.model)
    dataset = load_dataset(args.logs)
    metrics = evaluate_model(model, dataset, horizon=args.horizon)
    write_metrics(metrics, args.output)
    print(f"[INFO] evaluated Koopman model on {dataset.sample_count} samples")
    print(f"[INFO] wrote metrics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

