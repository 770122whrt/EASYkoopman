from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent


def resolve_package_asset(relative_path: str | Path) -> Path:
    """Resolve an existing file without allowing paths outside ``easyuuv_nc``."""

    requested_path = Path(relative_path)
    if requested_path.is_absolute():
        raise ValueError("Asset path must be relative to the package root")

    resolved_path = (PACKAGE_ROOT / requested_path).resolve()
    try:
        resolved_path.relative_to(PACKAGE_ROOT)
    except ValueError as exc:
        raise ValueError("Asset path must resolve inside the package") from exc

    if not resolved_path.is_file():
        raise FileNotFoundError(f"Package asset is not a file: {relative_path}")
    return resolved_path


EMBODIMENT_USD_PATH = resolve_package_asset("data/embodiment/embodiment.usd")
