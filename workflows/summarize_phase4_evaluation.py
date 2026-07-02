from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.evaluation_logs import build_phase4_report, render_markdown_report


def _collect_logs(args: argparse.Namespace) -> list[Path]:
    log_paths = [Path(path) for path in (args.logs or [])]
    for pattern in args.glob or []:
        log_paths.extend(Path(path) for path in glob.glob(pattern))
    unique_paths = sorted({path for path in log_paths})
    if not unique_paths:
        raise ValueError("Provide at least one --logs path or --glob pattern")
    return unique_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize Phase 4 controller evaluation JSONL logs.")
    parser.add_argument("--logs", nargs="*", default=[], help="Explicit Koopman JSONL log paths.")
    parser.add_argument("--glob", action="append", default=[], help="Glob pattern for Koopman JSONL log paths.")
    parser.add_argument("--output-json", required=True, type=Path, help="Output metrics summary JSON.")
    parser.add_argument("--output-md", required=True, type=Path, help="Output metrics summary Markdown.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_paths = _collect_logs(args)
    report = build_phase4_report(log_paths)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.write_text(render_markdown_report(report), encoding="utf-8")
    print(f"[INFO] wrote Phase 4 metrics JSON to {args.output_json}")
    print(f"[INFO] wrote Phase 4 metrics Markdown to {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
