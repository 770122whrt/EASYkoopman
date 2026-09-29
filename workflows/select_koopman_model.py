from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.selection import select_model_from_sweep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a Koopman model from a Phase 2.5 sweep summary.")
    parser.add_argument("--sweep-results", required=True, type=Path, help="sweep_results.json path.")
    parser.add_argument("--output", required=True, type=Path, help="selected_model_manifest.json path.")
    args = parser.parse_args(argv)

    manifest = select_model_from_sweep(args.sweep_results, args.output)
    print(f"[INFO] wrote selected model manifest to {args.output}")
    print(f"[INFO] gate_status={manifest['gate_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
