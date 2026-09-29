"""Verify current sources or explicitly supplied, immutable historical archives.

Archive verification never extracts files and never labels current execution as
historical execution. A historical collection identity and the current analysis
identity are separate fields in all new analysis reports.
"""
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINTS = (
    "workflows.collect_disturbance_data", "workflows.disturbance_data",
    "workflows.fit_disturbance", "workflows.evaluate_disturbance",
    "workflows.prepare_disturbance", "workflows.solve_disturbance",
    "workflows.freeze_support", "workflows.source_freeze",
    "koopman.control_solver", "easyuuv_nc.env.easyuuv_env",
    "easyuuv_nc.task_registration", "easyuuv_nc.control",
)
DATA_FILES = (
    "experiments/phase9/v86/protocol.json", "experiments/phase9/v87/protocol.json",
    "experiments/phase9/v88/protocol.json",
    "experiments/artifacts/physical.json",
    "experiments/artifacts/model.json",
    "experiments/artifacts/support.json",
    "easyuuv_nc/data/embodiment/embodiment.usd",
    "easyuuv_nc/data/embodiment/Props/instanceable_meshes.usd",
    "easyuuv_nc/data/embodiment/config.yaml",
)


def _path(name):
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("source_path:" + str(name))
    return PurePosixPath(name)


def _record(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("source_duplicate_key:" + key)
            result[key] = value
        return result
    record = json.loads(payload, object_pairs_hook=unique)
    files = record.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("source_files")
    for name, digest in files.items():
        _path(name)
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("source_digest:" + name)
    return record


def verify(path, *, root=ROOT, source_archive=None):
    """Verify every declared source; historical schemas require an explicit tar.

    Current freezes are always checked against the execution tree, even when an
    archive is supplied. Historical archives must contain exactly their declared
    files plus, optionally, one byte-identical embedded manifest.
    """
    payload = Path(path).read_bytes()
    record = _record(payload)
    digest = hashlib.sha256(payload).hexdigest()
    current = record.get("schema") == "current-source-freeze"
    if not current and record.get("schema") not in ("v86-source-freeze", "v87-source-freeze", "v88-source-freeze"):
        raise ValueError("source_schema")
    if not current and source_archive is None:
        raise ValueError("source_archive_required")
    if current:
        base = Path(root).resolve()
        for name, expected in record["files"].items():
            target = (base / name).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                raise ValueError("source_missing:" + name)
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError("source_hash:" + name)
    archive_sha = None
    if source_archive is not None:
        archive_path = Path(source_archive)
        archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        found, seen = set(), set()
        embedded = 0
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive:
                name = member.name.rstrip("/") if member.isdir() else member.name
                _path(name)
                if name in seen:
                    raise ValueError("source_duplicate_member:" + name)
                seen.add(name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("source_nonregular_member:" + name)
                body = archive.extractfile(member).read()
                if name in record["files"]:
                    if hashlib.sha256(body).hexdigest() != record["files"][name]:
                        raise ValueError("source_hash:" + name)
                    found.add(name)
                elif "/" not in name and name.endswith("manifest.json") and body == payload and embedded == 0:
                    embedded += 1
                else:
                    raise ValueError("source_unlisted_member:" + name)
        if found != set(record["files"]):
            raise ValueError("source_archive_missing:" + ",".join(sorted(set(record["files"]) - found)))
    return dict(source_manifest_sha256=digest,
                historical_source_manifest_sha256=None if current else digest,
                source_archive_sha256=archive_sha, verified_files=len(record["files"]))


def source_paths(root=ROOT, entry_points=ENTRY_POINTS, data_files=DATA_FILES):
    """Static local-import closure, including local module strings used dynamically.

    Import statements inside functions and package initializers are included.
    Explicit entry points cover environment registration and solver subprocesses;
    local dotted string constants cover importlib and gym entry-point names.
    """
    root = Path(root).resolve()
    pending = list(entry_points)
    visited, paths = set(), set()

    def locate(module):
        stem = root.joinpath(*module.split("."))
        for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
            if candidate.is_file():
                return candidate
        return None

    for module in entry_points:
        if locate(module) is None:
            raise ValueError("source_entry_missing:" + module)
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        path = locate(module)
        if path is None:
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError("source_external_path")
        paths.add(path.relative_to(root).as_posix())
        parts = module.split(".")
        for index in range(1, len(parts)):
            prefix = ".".join(parts[:index])
            if (root.joinpath(*parts[:index]) / "__init__.py").is_file():
                pending.append(prefix)
        package = parts if path.name == "__init__.py" else parts[:-1]
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = ".".join(prefix + ([node.module] if node.module else []))
                if base:
                    pending.append(base)
                    pending.extend(base + "." + alias.name for alias in node.names if alias.name != "*")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.split(":", 1)[0]
                if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", value) and locate(value):
                    pending.append(value)
    for name in data_files:
        _path(name)
        if not (root / name).is_file():
            raise ValueError("source_data_missing:" + name)
        paths.add(name)
    return sorted(paths)


def analysis_identity(root=ROOT):
    """Identity of the sources actually used for this current analysis."""
    root = Path(root)
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
             for name in source_paths(root)}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return dict(schema="current-analysis-source-identity", content_sha256=digest, files=files)
