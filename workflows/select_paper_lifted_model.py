from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.paper_lifted_selection import select_paper_lifted_from_sweep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a paper-style lifted EDMD comparison backend from a sweep.")
    parser.add_argument("--sweep-results", required=True, type=Path, help="Phase 2.5 sweep_results.json path.")
    parser.add_argument("--output", required=True, type=Path, help="paper_lifted_manifest.json output path.")
    args = parser.parse_args(argv)

    manifest = select_paper_lifted_from_sweep(args.sweep_results, args.output)
    print(f"[INFO] wrote paper lifted manifest to {args.output}")
    print(f"[INFO] gate_status={manifest['gate_status']}")
    print(f"[INFO] selected_candidate_id={manifest.get('selected_candidate_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
