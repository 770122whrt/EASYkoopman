from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from workflows import collect_koopman_v21_identification as collector


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.excludesFile=", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _clean_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "phase81@example.invalid")
    _git(repository, "config", "user.name", "Phase 8.1 Test")
    (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-m", "fixture")
    return repository, _git(repository, "rev-parse", "HEAD")


def test_repository_commit_derives_clean_head_and_matches_optional_expected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, head = _clean_repository(tmp_path)
    monkeypatch.setattr(collector, "PROJECT_ROOT", repository)

    assert collector._repository_commit() == head
    assert collector._repository_commit(expected_source_commit=head) == head


@pytest.mark.parametrize(
    ("expected", "reason"),
    [
        ("A" * 40, "expected_source_commit_invalid"),
        ("0" * 40, "source_commit_mismatch"),
    ],
)
def test_repository_commit_rejects_invalid_or_mismatched_expected_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expected: str,
    reason: str,
) -> None:
    repository, _head = _clean_repository(tmp_path)
    monkeypatch.setattr(collector, "PROJECT_ROOT", repository)

    with pytest.raises(RuntimeError, match=reason):
        collector._repository_commit(expected_source_commit=expected)


@pytest.mark.parametrize(
    ("dirty_kind", "reason"),
    [
        ("tracked", "source_worktree_tracked_dirty"),
        ("untracked", "source_worktree_untracked_dirty"),
    ],
)
def test_repository_commit_rejects_all_tracked_and_untracked_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dirty_kind: str,
    reason: str,
) -> None:
    repository, _head = _clean_repository(tmp_path)
    monkeypatch.setattr(collector, "PROJECT_ROOT", repository)
    if dirty_kind == "tracked":
        (repository / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    else:
        (repository / "untracked.py").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=reason):
        collector._repository_commit()


@pytest.mark.parametrize(
    ("dirty_kind", "reason"),
    [
        ("tracked", "source_worktree_tracked_dirty"),
        ("untracked", "source_worktree_untracked_dirty"),
    ],
)
def test_main_rejects_dirty_source_before_runner_or_output_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dirty_kind: str,
    reason: str,
) -> None:
    repository, _head = _clean_repository(tmp_path)
    monkeypatch.setattr(collector, "PROJECT_ROOT", repository)
    monkeypatch.setattr(
        collector,
        "require_canonical_d23_approval_v21",
        lambda *_args, **_kwargs: {"decision": "approved"},
    )
    if dirty_kind == "tracked":
        (repository / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    else:
        (repository / "untracked.py").write_text("dirty\n", encoding="utf-8")
    touched: list[bool] = []

    def forbidden_runner(**_kwargs):
        touched.append(True)
        raise AssertionError("runner accessed before source validation")

    monkeypatch.setattr(collector, "_run_authorized_collection", forbidden_runner)
    output_root = repository / "output"
    status = collector.main(
        [
            "--approval-record",
            "approval.json",
            "--role-protocol",
            "role.json",
            "--analysis-policy",
            "policy.json",
            "--output-root",
            str(output_root),
        ]
    )

    assert status == 1
    assert reason in capsys.readouterr().err
    assert touched == []
    assert not output_root.exists()


def test_main_passes_clean_derived_head_to_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, head = _clean_repository(tmp_path)
    monkeypatch.setattr(collector, "PROJECT_ROOT", repository)
    monkeypatch.setattr(
        collector,
        "require_canonical_d23_approval_v21",
        lambda *_args, **_kwargs: {"decision": "approved"},
    )
    observed: list[str] = []

    def runner(**kwargs):
        observed.append(kwargs["source_commit"])
        return 0

    monkeypatch.setattr(collector, "_run_authorized_collection", runner)
    status = collector.main(
        [
            "--approval-record",
            "approval.json",
            "--role-protocol",
            "role.json",
            "--analysis-policy",
            "policy.json",
            "--output-root",
            str(repository / "output"),
        ]
    )

    assert status == 0
    assert observed == [head]
    assert not (repository / "output").exists()


def test_main_rejects_expected_commit_mismatch_before_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository, _head = _clean_repository(tmp_path)
    monkeypatch.setattr(collector, "PROJECT_ROOT", repository)
    monkeypatch.setattr(
        collector,
        "require_canonical_d23_approval_v21",
        lambda *_args, **_kwargs: {"decision": "approved"},
    )
    touched: list[bool] = []

    def forbidden_runner(**_kwargs):
        touched.append(True)
        raise AssertionError("runner accessed after source mismatch")

    monkeypatch.setattr(collector, "_run_authorized_collection", forbidden_runner)
    status = collector.main(
        [
            "--approval-record",
            "approval.json",
            "--role-protocol",
            "role.json",
            "--analysis-policy",
            "policy.json",
            "--output-root",
            str(repository / "output"),
            "--source-commit",
            "0" * 40,
        ]
    )

    assert status == 1
    assert "source_commit_mismatch" in capsys.readouterr().err
    assert touched == []
    assert not (repository / "output").exists()
