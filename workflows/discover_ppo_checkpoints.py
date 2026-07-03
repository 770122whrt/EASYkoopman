from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_SEARCH_ROOTS = (
    Path("logs/rsl_rl/easyuuv"),
    Path("/root/EASYkoopman/logs/rsl_rl/easyuuv"),
    Path("/root/IsaacLab/logs/rsl_rl/easyuuv"),
)


def discover_ppo_checkpoints(search_roots: list[str | Path] | tuple[str | Path, ...] | None = None) -> dict[str, Any]:
    roots = [Path(root) for root in (search_roots or DEFAULT_SEARCH_ROOTS)]
    paths: list[str] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        candidates = list(root.rglob("model_*.pt")) + list(root.rglob("*.pt"))
        for candidate in sorted(candidates, key=lambda path: str(path), reverse=True):
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(str(candidate))
    return {
        "checkpoint_found": bool(paths),
        "count": len(paths),
        "paths": paths,
        "search_roots": [str(root) for root in roots],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover EasyUUV PPO/RSL-RL checkpoints.")
    parser.add_argument("--root", action="append", default=None, help="Search root. Can be passed multiple times.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = discover_ppo_checkpoints(args.root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"checkpoint_found={str(result['checkpoint_found']).lower()}")
        print(f"count={result['count']}")
        for path in result["paths"]:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
