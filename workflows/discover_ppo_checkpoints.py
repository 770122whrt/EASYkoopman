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


def _checkpoint_sort_key(path: Path) -> tuple[int, float, str]:
    is_model_checkpoint = 1 if path.name.startswith("model_") else 0
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (is_model_checkpoint, mtime, str(path))


def discover_ppo_checkpoints(
    search_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
    explicit_checkpoint: str | Path | None = None,
) -> dict[str, Any]:
    roots = [Path(root) for root in (search_roots or DEFAULT_SEARCH_ROOTS)]
    candidates_by_path: dict[Path, Path] = {}
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        candidates = list(root.rglob("model_*.pt")) + list(root.rglob("*.pt"))
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates_by_path[resolved] = candidate

    candidates = sorted(candidates_by_path.values(), key=_checkpoint_sort_key, reverse=True)
    paths: list[str] = []
    selected_checkpoint: str | None = None
    selected_rule = "none"

    if explicit_checkpoint is not None:
        explicit_path = Path(explicit_checkpoint)
        paths.append(str(explicit_path))
        selected_checkpoint = str(explicit_path)
        selected_rule = "explicit_path"

    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str not in paths:
            paths.append(candidate_str)

    if selected_checkpoint is None and candidates:
        selected_checkpoint = str(candidates[0])
        selected_rule = "latest_mtime_model_pt" if candidates[0].name.startswith("model_") else "latest_mtime_pt"

    return {
        "checkpoint_found": bool(paths),
        "count": len(paths),
        "paths": paths,
        "search_roots": [str(root) for root in roots],
        "selected_checkpoint": selected_checkpoint,
        "selected_rule": selected_rule,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover EasyUUV PPO/RSL-RL checkpoints.")
    parser.add_argument("--root", action="append", default=None, help="Search root. Can be passed multiple times.")
    parser.add_argument("--checkpoint", type=str, default=None, help="Explicit checkpoint path to select.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = discover_ppo_checkpoints(args.root, explicit_checkpoint=args.checkpoint)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"checkpoint_found={str(result['checkpoint_found']).lower()}")
        print(f"count={result['count']}")
        print(f"selected_checkpoint={result['selected_checkpoint']}")
        print(f"selected_rule={result['selected_rule']}")
        for path in result["paths"]:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
