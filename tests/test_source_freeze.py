"""Current workflow provenance rejects altered or ambiguous historical bundles."""
import hashlib
import io
import json
import tarfile

import pytest

from workflows import source_freeze


def fixture_manifest(tmp_path, schema="v88-source-freeze"):
    payload = b"original source\n"
    record = {"schema": schema, "files": {"workflows/sample.py": hashlib.sha256(payload).hexdigest()}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path, payload


def bundle(path, items):
    with tarfile.open(path, "w:gz") as archive:
        for name, value in items:
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))


def test_historical_source_requires_explicit_archive(tmp_path):
    path, _ = fixture_manifest(tmp_path)
    with pytest.raises(ValueError, match="source_archive_required"):
        source_freeze.verify(path, root=tmp_path)


def test_historical_source_verified_from_archive_not_current_tree(tmp_path):
    path, payload = fixture_manifest(tmp_path)
    archive = tmp_path / "source.tar.gz"
    bundle(archive, [("workflows/sample.py", payload), ("v88-manifest.json", path.read_bytes())])
    result = source_freeze.verify(path, root=tmp_path, source_archive=archive)
    assert result["historical_source_manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["source_archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert result["verified_files"] == 1


@pytest.mark.parametrize("items", [
    [("workflows/sample.py", b"tampered")],
    [],
    [("workflows/sample.py", b"original source\n"), ("workflows/sample.py", b"original source\n")],
    [("../escape.py", b"x")],
    [("C:/escape.py", b"x")],
    [("workflows/sample.py", b"original source\n"), ("unlisted.py", b"x")],
])
def test_invalid_historical_bundle_rejected(tmp_path, items):
    path, _ = fixture_manifest(tmp_path)
    archive = tmp_path / "source.tar.gz"
    bundle(archive, items)
    with pytest.raises(ValueError):
        source_freeze.verify(path, root=tmp_path, source_archive=archive)


def test_current_freeze_checks_live_tree_and_rejects_tamper(tmp_path):
    path, payload = fixture_manifest(tmp_path, "current-source-freeze")
    source = tmp_path / "workflows" / "sample.py"
    source.parent.mkdir()
    source.write_bytes(payload)
    result = source_freeze.verify(path, root=tmp_path)
    assert result["historical_source_manifest_sha256"] is None
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source_hash"):
        source_freeze.verify(path, root=tmp_path)


def test_current_package_contains_configs_dynamic_entries_and_asset_dependencies(tmp_path):
    from workflows.prepare_disturbance import prepare
    from workflows.disturbance_data import verify_manifest
    output = tmp_path / "release"
    summary = prepare(output)
    record = json.loads((output / "manifest.json").read_text())
    required = {
        "workflows/collect_disturbance_data.py", "workflows/disturbance_protocol.py",
        "koopman/control_solver.py", "easyuuv_nc/control.py",
        "easyuuv_nc/env/easyuuv_env.py", "easyuuv_nc/task_registration.py",
        "experiments/phase9/v86/protocol.json", "experiments/phase9/v87/protocol.json",
        "experiments/phase9/v88/protocol.json",
        "easyuuv_nc/data/embodiment/embodiment.usd",
        "easyuuv_nc/data/embodiment/Props/instanceable_meshes.usd",
        "easyuuv_nc/data/embodiment/config.yaml",
    }
    assert required <= set(record["files"])
    assert not any(name.startswith("tests/") for name in record["files"])
    assert verify_manifest(output / "manifest.json") == summary["manifest_sha256"]
    assert source_freeze.verify(output / "manifest.json", source_archive=output / "source.tar.gz")["verified_files"] == summary["files"]


def test_shared_training_and_metrics_preserve_original_behavior():
    import numpy as np
    from workflows.fit_disturbance import training_arrays
    from workflows.disturbance_protocol import get_protocol
    from workflows.disturbance_data import errors
    from control_fixtures import oracle
    cases = [case for case in get_protocol("v87").cases() if case["role"] == "train"]
    rng = np.random.default_rng(24)
    episodes = [dict(case=case, states=rng.normal(size=(1281, 11)),
                     inputs=rng.normal(size=(1280, 6)), trace_sha256=str(i))
                for i, case in enumerate(cases)]
    assert [hashlib.sha256(a.tobytes()).hexdigest() for a in training_arrays(episodes)] == oracle()["training_hashes"]
    prediction, truth = rng.normal(size=(2, 80, 11))
    assert errors(prediction, truth) == oracle()["errors"]


def test_frozen_model_loader_preserves_model_record():
    from workflows.disturbance_data import frozen_model, MODEL_PATH, ROOT
    from control_fixtures import oracle
    current, _ = frozen_model()
    digest = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == oracle()["model_record_hash"]


def test_explicit_dynamic_entry_cannot_be_silently_omitted(tmp_path):
    with pytest.raises(ValueError, match="source_entry_missing"):
        source_freeze.source_paths(tmp_path, entry_points=("missing.worker",), data_files=())


def test_archive_does_not_bypass_current_source_tamper(tmp_path):
    path, payload = fixture_manifest(tmp_path, "current-source-freeze")
    source = tmp_path / "workflows" / "sample.py"
    source.parent.mkdir()
    source.write_bytes(b"changed")
    archive = tmp_path / "source.tar.gz"
    bundle(archive, [("workflows/sample.py", payload)])
    with pytest.raises(ValueError, match="source_hash"):
        source_freeze.verify(path, root=tmp_path, source_archive=archive)


def test_manifest_duplicate_paths_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    digest = hashlib.sha256(b"content").hexdigest()
    path.write_text('{"schema":"v88-source-freeze","files":{"sample.py":"' + digest
                    + '","sample.py":"' + digest + '"}}')
    with pytest.raises(ValueError, match="source_duplicate_key"):
        source_freeze.verify(path, root=tmp_path)


def test_archive_links_rejected(tmp_path):
    path, _ = fixture_manifest(tmp_path)
    archive_path = tmp_path / "source.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        link = tarfile.TarInfo("workflows/sample.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "outside.py"
        archive.addfile(link)
    with pytest.raises(ValueError, match="source_nonregular_member"):
        source_freeze.verify(path, root=tmp_path, source_archive=archive_path)
