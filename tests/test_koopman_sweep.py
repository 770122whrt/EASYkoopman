import json
import shutil

from koopman.splits import create_explicit_split, write_split_manifest
from koopman.sweep import run_sweep

from tests.test_koopman_dataset import FIXTURE


def _copy_fixture(tmp_path, name):
    path = tmp_path / name
    shutil.copyfile(FIXTURE, path)
    return path


def test_sweep_writes_candidates_and_baselines(tmp_path):
    train = _copy_fixture(tmp_path, "train.jsonl")
    validation = _copy_fixture(tmp_path, "validation.jsonl")
    test = _copy_fixture(tmp_path, "test.jsonl")
    split_path = tmp_path / "split.json"
    write_split_manifest(
        create_explicit_split(train_logs=[train], validation_logs=[validation], test_logs=[test]),
        split_path,
    )

    summary = run_sweep(
        split_path,
        tmp_path / "sweep",
        ridge_values=(1e-4,),
        lifting_variants=("linear", "selected_quadratic"),
        normalization_modes=("off",),
    )

    model_classes = {candidate["model_class"] for candidate in summary["candidates"]}
    assert {"direct_state", "paper_lifted_edmd"} <= model_classes
    assert {"persistence", "simple_linear"} <= set(summary["baselines"])
    assert summary["candidates"][0]["validation_metrics"]["sample_count"] == 4
    assert json.loads((tmp_path / "sweep" / "sweep_results.json").read_text(encoding="utf-8"))["candidates"]
