"""The deployed workflows package is a PEP420 namespace, not a mutable list."""
from types import SimpleNamespace
from pathlib import Path
import sys
import json
import os
import subprocess


class NamespacePaths:
    def __iter__(self): return iter(['/frozen/workflows'])


def test_readiness_bootstrap_preserves_namespace_paths(monkeypatch, tmp_path):
    from workflows.check_rate30_worker_v67 import paths
    namespace = SimpleNamespace(__name__='workflows', __path__=NamespacePaths())
    import koopman
    monkeypatch.setattr(koopman, '__path__', NamespacePaths())
    monkeypatch.setitem(sys.modules, 'workflows', namespace)
    monkeypatch.setattr(sys, 'argv', ['check.py', '--release-root', str(tmp_path)])
    monkeypatch.setattr(sys, 'path', list(sys.path))
    assert paths() == tmp_path.resolve()
    assert isinstance(namespace.__path__, list)
    assert namespace.__path__[0].endswith('workflows')
    assert namespace.__path__[1:] == ['/frozen/workflows']


def test_packaged_collector_bootstrap_uses_all_three_addon_packages(tmp_path):
    from workflows.package_rate30_v67 import package
    root = Path(__file__).resolve().parents[1]
    addon = tmp_path/'addon'
    package(root, addon)
    code = '''import importlib.util,sys,json
from pathlib import Path
entry=Path(sys.argv[1]);root=sys.argv[2]
spec=importlib.util.spec_from_file_location('collector_under_test',entry)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def inspect_paths(root,output,case):
 import koopman,workflows,easyuuv_nc
 for package in (koopman,workflows,easyuuv_nc):
  assert Path(package.__path__[0])==entry.parents[1]/package.__name__
 assert case['control_rate_hz']==30 and case['controls']==60
 print(json.dumps(dict(bootstrap=True,configuration=case['configuration'])))
 return 0
module.diagnose=inspect_paths
sys.argv=[str(entry),'--release-root',root,'--output',str(entry.parent/'unused'),'--case','base-pitch-feedback']
raise SystemExit(module.main())
'''
    environment = os.environ.copy()
    environment.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-B', '-c', code,
        str(addon/'bin/collect_effects_v67.py'), str(root)], env=environment,
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['bootstrap'] is True
