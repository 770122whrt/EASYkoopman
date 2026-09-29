import json
import shutil

import pytest

from koopman.splits import (
    DataInsufficientError,
    SplitManifest,
    create_explicit_split,
    read_split_manifest,
    validate_split_manifest,
    write_split_manifest,
)

from tests.test_koopman_dataset import FIXTURE


def _copy_fixture(tmp_path, name):
    path = tmp_path / name
    shutil.copyfile(FIXTURE, path)
    return path


def test_split_manifest_round_trips_existing_log_paths(tmp_path):
    train = _copy_fixture(tmp_path, "train.jsonl")
    validation = _copy_fixture(tmp_path, "validation.jsonl")
    test = _copy_fixture(tmp_path, "test.jsonl")

    manifest = create_explicit_split(
        train_logs=[train],
        validation_logs=[validation],
        test_logs=[test],
        seed=7,
        notes="fixture split",
    )
    path = tmp_path / "split_manifest.json"
    write_split_manifest(manifest, path)

    loaded = read_split_manifest(path)

    assert loaded.seed == 7
    assert loaded.notes == "fixture split"
    assert loaded.train_logs == (str(train),)
    assert loaded.validation_logs == (str(validation),)
    assert loaded.test_logs == (str(test),)
    assert json.loads(path.read_text(encoding="utf-8"))["split_rule"] == "explicit"


def test_split_manifest_rejects_overlapping_logs(tmp_path):
    train = _copy_fixture(tmp_path, "train.jsonl")
    validation = _copy_fixture(tmp_path, "validation.jsonl")

    manifest = SplitManifest(
        train_logs=(str(train),),
        validation_logs=(str(validation),),
        test_logs=(str(train),),
        split_rule="explicit",
        seed=1,
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_split_manifest(manifest)


def test_final_gate_requires_validation_and_test_logs(tmp_path):
    train = _copy_fixture(tmp_path, "train.jsonl")
    manifest = SplitManifest(
        train_logs=(str(train),),
        validation_logs=(),
        test_logs=(),
        split_rule="explicit",
        seed=1,
    )

    with pytest.raises(DataInsufficientError):
        validate_split_manifest(manifest, final_gate=True)
