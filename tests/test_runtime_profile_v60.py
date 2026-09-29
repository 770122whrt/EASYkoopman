"""Profiling must preserve failures and never turn diagnostics into acceptance."""
import importlib
import json
from pathlib import Path

import pytest


def api():
    path = Path(__file__).resolve().parents[1] / 'workflows/runtime_profile_v60.py'
    assert path.exists(), 'bounded diagnostic implementation missing'
    return importlib.import_module('workflows.runtime_profile_v60')


def test_profile_preserves_return_and_records_calls(tmp_path):
    m = api()
    def work(): return sum(range(50))
    assert m.profile_call(work, tmp_path) == 1225
    r = json.loads((tmp_path/'profile.json').read_text())
    assert r['diagnostic_only'] is True and r['runtime_qualified'] is False
    assert any(q['function']=='work' and q['calls']==1 for q in r['functions'])
    assert (tmp_path/'profile.pstats').is_file()


def test_profile_preserves_original_exception_and_partial_measurement(tmp_path):
    m = api()
    error = ValueError('runtime_full_cycle_deadline')
    def fail(): raise error
    with pytest.raises(ValueError) as got:
        m.profile_call(fail, tmp_path)
    assert got.value is error
    r = json.loads((tmp_path/'profile.json').read_text())
    assert any(q['function']=='fail' for q in r['functions'])


def test_diagnostic_output_cannot_touch_frozen_source(tmp_path):
    m = api(); root=tmp_path/'frozen'; root.mkdir()
    for output in (root, root/'results'):
        with pytest.raises(ValueError, match='outside_frozen_release'):
            m.prepare_output(root, output)
    output=tmp_path/'diagnostic'
    m.prepare_output(root, output)
    with pytest.raises(FileExistsError): m.prepare_output(root, output)
