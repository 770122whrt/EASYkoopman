from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.gate_report import write_gate_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a Phase 2.5 Koopman gate report markdown file.")
    parser.add_argument("--manifest", required=True, type=Path, help="selected_model_manifest.json path.")
    parser.add_argument("--sweep-results", required=True, type=Path, help="sweep_results.json path.")
    parser.add_argument("--output", required=True, type=Path, help="gate_report.md path.")
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    sweep = json.loads(args.sweep_results.read_text(encoding="utf-8"))
    write_gate_report(manifest, sweep, args.output)
    print(f"[INFO] wrote gate report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
