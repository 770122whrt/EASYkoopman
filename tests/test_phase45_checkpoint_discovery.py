import json
import os

from workflows.discover_ppo_checkpoints import discover_ppo_checkpoints, main


def test_discover_ppo_checkpoints_finds_model_files_in_priority_order(tmp_path):
    first_root = tmp_path / "logs" / "rsl_rl" / "easyuuv"
    second_root = tmp_path / "other" / "logs" / "rsl_rl" / "easyuuv"
    first_root.mkdir(parents=True)
    second_root.mkdir(parents=True)
    later = first_root / "model_100.pt"
    earlier = second_root / "model_001.pt"
    later.write_text("later", encoding="utf-8")
    earlier.write_text("earlier", encoding="utf-8")
    os.utime(earlier, (100, 100))
    os.utime(later, (200, 200))

    result = discover_ppo_checkpoints([first_root, second_root])

    assert result["checkpoint_found"] is True
    assert result["count"] == 2
    assert result["paths"][0] == str(later)
    assert result["paths"][1] == str(earlier)
    assert result["selected_checkpoint"] == str(later)
    assert result["selected_rule"] == "latest_mtime_model_pt"


def test_discover_ppo_checkpoints_reports_missing_roots(tmp_path):
    result = discover_ppo_checkpoints([tmp_path / "missing"])

    assert result["checkpoint_found"] is False
    assert result["count"] == 0
    assert result["paths"] == []
    assert result["selected_checkpoint"] is None
    assert result["selected_rule"] == "none"


def test_discover_ppo_checkpoints_cli_outputs_json(tmp_path, capsys):
    root = tmp_path / "logs" / "rsl_rl" / "easyuuv"
    root.mkdir(parents=True)
    (root / "model_000.pt").write_text("checkpoint", encoding="utf-8")

    assert main(["--root", str(root), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["checkpoint_found"] is True
    assert payload["count"] == 1
    assert payload["selected_checkpoint"].endswith("model_000.pt")
    assert payload["selected_rule"] == "latest_mtime_model_pt"


def test_discover_ppo_checkpoints_prefers_explicit_checkpoint(tmp_path):
    root = tmp_path / "logs" / "rsl_rl" / "easyuuv"
    root.mkdir(parents=True)
    discovered = root / "model_000.pt"
    explicit = tmp_path / "manual.pt"
    discovered.write_text("discovered", encoding="utf-8")
    explicit.write_text("explicit", encoding="utf-8")

    result = discover_ppo_checkpoints([root], explicit_checkpoint=explicit)

    assert result["checkpoint_found"] is True
    assert result["selected_checkpoint"] == str(explicit)
    assert result["selected_rule"] == "explicit_path"
    assert result["paths"][0] == str(explicit)


def test_discover_ppo_checkpoints_prefers_model_pt_over_newer_generic_file(tmp_path):
    root = tmp_path / "logs" / "rsl_rl" / "easyuuv"
    root.mkdir(parents=True)
    model = root / "model_001.pt"
    generic = root / "policy.pt"
    model.write_text("model", encoding="utf-8")
    generic.write_text("generic", encoding="utf-8")
    os.utime(model, (100, 100))
    os.utime(generic, (200, 200))

    result = discover_ppo_checkpoints([root])

    assert result["selected_checkpoint"] == str(model)
    assert result["selected_rule"] == "latest_mtime_model_pt"
