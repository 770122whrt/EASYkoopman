"""Hash-check all pulled evidence; never replace a differing local file."""
import hashlib
import json
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parent
archive=root/'server-evidence.tar.gz'
expected='28cbb2f453181358e3acc7d08de11332f88fc1c7c0043d5a74807d948f27cab5'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
target=(root/'server').resolve()
with tarfile.open(archive,'r:gz') as tar:
    members=tar.getmembers()
    inventory=json.load(tar.extractfile('evidence-inventory.json'))
    assert {m.name for m in members}==set(inventory['files'])|{'evidence-inventory.json'}
    for m in members:
        path=(target/m.name).resolve()
        assert path.is_relative_to(target) and m.isfile()
        content=tar.extractfile(m).read()
        if m.name in inventory['files']:
            entry=inventory['files'][m.name]
            assert len(content)==entry['bytes'] and hashlib.sha256(content).hexdigest()==entry['sha256']
        if path.exists():
            assert path.read_bytes()==content,'existing_local_file_differs:'+m.name
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(content)
for name,entry in inventory['files'].items():
    data=(target/name).read_bytes()
    assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
result=dict(accepted=True,archive_sha256=expected,verified_files=len(inventory['files']))
with (root/'local/archive-validation.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result))
