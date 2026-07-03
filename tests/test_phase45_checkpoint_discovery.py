import json

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

    result = discover_ppo_checkpoints([first_root, second_root])

    assert result["checkpoint_found"] is True
    assert result["count"] == 2
    assert result["paths"][0] == str(later)
    assert result["paths"][1] == str(earlier)


def test_discover_ppo_checkpoints_reports_missing_roots(tmp_path):
    result = discover_ppo_checkpoints([tmp_path / "missing"])

    assert result["checkpoint_found"] is False
    assert result["count"] == 0
    assert result["paths"] == []


def test_discover_ppo_checkpoints_cli_outputs_json(tmp_path, capsys):
    root = tmp_path / "logs" / "rsl_rl" / "easyuuv"
    root.mkdir(parents=True)
    (root / "model_000.pt").write_text("checkpoint", encoding="utf-8")

    assert main(["--root", str(root), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["checkpoint_found"] is True
    assert payload["count"] == 1
