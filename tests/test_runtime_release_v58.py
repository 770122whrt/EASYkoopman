"""Additive packaging must retain every historical asset/source byte."""
import hashlib
import json
from pathlib import Path
import pytest


def setup(tmp_path):
    origin=tmp_path/'origin';dest=tmp_path/'assets';origin.mkdir();dest.mkdir()
    (origin/'old.py').write_bytes(b'old immutable');(dest/'old.py').write_bytes(b'old immutable')
    (origin/'new.py').write_bytes(b'new module')
    return origin,dest


def test_additive_overlay_preserves_frozen_files_and_counts_only_added_bytes(tmp_path):
    from workflows.package_runtime_v58 import plan_overlay,apply_overlay
    source,dest=setup(tmp_path);before=(dest/'old.py').stat().st_mtime_ns
    plan=plan_overlay(source,dest,['old.py','new.py'],maximum_new_bytes=100)
    assert plan['new_bytes']==10
    apply_overlay(plan)
    assert (dest/'old.py').stat().st_mtime_ns==before and (dest/'new.py').read_bytes()==b'new module'


@pytest.mark.parametrize('bad',['conflict','source_missing','escape','budget'])
def test_invalid_overlay_fails_before_any_new_file_written(tmp_path,bad):
    from workflows.package_runtime_v58 import plan_overlay
    source,dest=setup(tmp_path);names=['new.py','old.py'];cap=100
    if bad=='conflict':(source/'old.py').write_bytes(b'changed')
    if bad=='source_missing':names.append('missing.py')
    if bad=='escape':names.append('../outside.py')
    if bad=='budget':cap=1
    with pytest.raises((ValueError,FileNotFoundError)):plan_overlay(source,dest,names,maximum_new_bytes=cap)
    assert sorted(p.name for p in dest.iterdir())==['old.py']


def test_source_changed_after_planning_cannot_be_copied(tmp_path):
    from workflows.package_runtime_v58 import plan_overlay,apply_overlay
    source,dest=setup(tmp_path);plan=plan_overlay(source,dest,['new.py'],maximum_new_bytes=100)
    (source/'new.py').write_bytes(b'changed')
    with pytest.raises(ValueError,match='source_changed'):apply_overlay(plan)
    assert not (dest/'new.py').exists()


def test_dependency_closure_includes_relative_imports_test_helpers_and_parents(tmp_path):
    from workflows.package_runtime_v58 import dependency_closure
    for rel,text in {'workflows/__init__.py':'','workflows/run.py':'from . import helper\nimport test_helper',
        'workflows/helper.py':'from koopman.kernel import value','koopman/__init__.py':'','koopman/kernel.py':'value=1',
        'tests/test_helper.py':'import pathlib'}.items():
        p=tmp_path/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    result=dependency_closure(tmp_path,['workflows/run.py'])
    assert set(result)=={'workflows/__init__.py','workflows/run.py','workflows/helper.py','koopman/__init__.py','koopman/kernel.py','tests/test_helper.py'}


def test_execution_release_requires_supervisor_and_fixed_resource_contract(tmp_path):
    from workflows.package_runtime_v58 import verify_executable_release
    from test_phase9_preflight_v57 import release
    release(tmp_path)
    with pytest.raises(ValueError,match='supervision'):verify_executable_release(tmp_path)
