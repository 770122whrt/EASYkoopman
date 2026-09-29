"""Diagnostic outputs must not dirty source; other changes still fail closed."""
from pathlib import Path
import subprocess

import pytest

from workflows import collect_koopman_v21_identification as collector


def test_trace_output_is_ignored_but_unknown_files_and_source_edits_are_rejected(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / '.gitignore').write_bytes((root / '.gitignore').read_bytes())
    source = tmp_path / 'controller.py'
    source.write_text('value = 1\n', encoding='utf-8')
    def git(*args):
        return subprocess.run(['git', '-c', 'core.excludesFile=', '-c', 'core.autocrlf=false',
            '-c', 'user.name=Trace package test', '-c', 'user.email=trace-test@localhost',
            *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    git('init')
    git('add', '--', '.gitignore', 'controller.py')
    git('commit', '-m', 'Test fixture')
    monkeypatch.setattr(collector, 'PROJECT_ROOT', tmp_path)
    expected = collector._repository_commit()
    output = tmp_path / 'tmp/phase8_3/first/trace.json'
    output.parent.mkdir(parents=True)
    output.write_text('{}', encoding='utf-8')
    assert collector._repository_commit() == expected
    unknown = tmp_path / 'tmp/unrelated.bin'
    unknown.write_bytes(b'unreviewed')
    with pytest.raises(RuntimeError, match='source_worktree_untracked_dirty'):
        collector._repository_commit()
    unknown.unlink()  # Only the exact file created by this fixture.
    source.write_text('value = 2\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='source_worktree_tracked_dirty'):
        collector._repository_commit()
