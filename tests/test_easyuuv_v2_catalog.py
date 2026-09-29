"""Isaac-free contract tests for the EasyUUV 2.0 embodiment catalog."""

from __future__ import annotations

import ast
import operator
from pathlib import Path
import subprocess
from typing import Any

import pytest

from easyuuv_nc.embodiments import (
    CONTROL_CHANNELS,
    EMBODIMENT_CONFIGS,
    INTERNAL_EMBODIMENTS,
    SUPPORTED_EMBODIMENTS,
    qualification_record,
)
from easyuuv_nc.thrust_allocation import declared_control_rank


PROJECT_ROOT = Path(__file__).resolve().parents[1]


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _literal_with_arithmetic(node: ast.AST) -> Any:
    """Evaluate the numeric/list/dict subset used by the snapshot config."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_literal_with_arithmetic(item) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal_with_arithmetic(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _literal_with_arithmetic(key): _literal_with_arithmetic(value)
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _literal_with_arithmetic(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](
            _literal_with_arithmetic(node.left),
            _literal_with_arithmetic(node.right),
        )
    raise AssertionError(f"unsupported snapshot config expression: {ast.dump(node)}")


def _snapshot_embodiment_configs() -> dict[str, dict[str, Any]]:
    provenance = (PROJECT_ROOT / "easyuuv_nc" / "SNAPSHOT_PROVENANCE.md").read_text(encoding="utf-8")
    snapshot_commit = next(
        line.split(":", maxsplit=1)[1].strip()
        for line in provenance.splitlines()
        if line.startswith("snapshot_commit:")
    )
    result = subprocess.run(
        ["git", "show", f"{snapshot_commit}:easyuuv_v2-main/env/easyuuv_env.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr

    tree = ast.parse(result.stdout)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "EasyUUVEnvCfg":
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if any(isinstance(target, ast.Name) and target.id == "embodiment_configs" for target in statement.targets):
                    return _literal_with_arithmetic(statement.value)
    raise AssertionError("snapshot EasyUUVEnvCfg.embodiment_configs assignment not found")


EXPECTED_PUBLIC_CONFIGURATIONS = (
    ("base", 8, (1, 1, 1, 1), 4),
    ("long_body", 8, (1, 1, 1, 1), 4),
    ("heavy_moderate", 8, (1, 1, 1, 1), 4),
    ("asymmetric", 8, (1, 1, 1, 1), 4),
    ("uuv6", 6, (1, 1, 1, 1), 4),
    ("uuv6_angled", 6, (1, 1, 1, 1), 4),
    ("uuv4", 4, (1, 1, 0, 1), 3),
    ("uuv4_angled", 4, (1, 1, 0, 1), 3),
)


def test_public_configuration_matrix_is_exact():
    assert CONTROL_CHANNELS == ("roll", "pitch", "yaw", "depth")
    assert SUPPORTED_EMBODIMENTS == tuple(row[0] for row in EXPECTED_PUBLIC_CONFIGURATIONS)
    assert INTERNAL_EMBODIMENTS == ("heavy_duty",)
    assert set(EMBODIMENT_CONFIGS) == set(SUPPORTED_EMBODIMENTS) | set(INTERNAL_EMBODIMENTS)

    records = [qualification_record(name) for name in SUPPORTED_EMBODIMENTS]
    assert "heavy_duty" not in {record["configuration"] for record in records}

    assert [
        (
            record["configuration"],
            record["thruster_count"],
            record["control_mask"],
            record["declared_control_rank"],
        )
        for record in records
    ] == list(EXPECTED_PUBLIC_CONFIGURATIONS)


@pytest.mark.parametrize("name, _count, _mask, expected_rank", EXPECTED_PUBLIC_CONFIGURATIONS)
def test_declared_control_rank_matches_public_qualification_matrix(
    name: str, _count: int, _mask: tuple[int, int, int, int], expected_rank: int
):
    assert declared_control_rank(EMBODIMENT_CONFIGS[name]) == expected_rank


def test_unknown_configuration_is_rejected_with_its_name():
    with pytest.raises(KeyError, match="unsupported_vehicle"):
        qualification_record("unsupported_vehicle")


def test_extracted_configs_deep_equal_the_recorded_snapshot():
    assert EMBODIMENT_CONFIGS == _snapshot_embodiment_configs()


def test_qualification_records_do_not_expose_mutable_catalog_references():
    record = qualification_record("uuv4")
    assert isinstance(record["control_channels"], tuple)
    assert isinstance(record["control_mask"], tuple)

    record["control_mask"] = (9, 9, 9, 9)
    assert qualification_record("uuv4")["control_mask"] == (1, 1, 0, 1)


@pytest.mark.parametrize(
    "relative_path",
    (
        "easyuuv_nc/env/easyuuv_env.py",
        "easyuuv_nc/workflows/train.py",
        "easyuuv_nc/workflows/adapt.py",
    ),
)
def test_runtime_consumers_use_the_canonical_catalog(relative_path: str):
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    if relative_path.endswith("easyuuv_env.py"):
        assert "EMBODIMENT_CONFIGS" in source
    else:
        assert "choices=SUPPORTED_EMBODIMENTS" in source

    assert 'choices=["base", "long_body"' not in source
