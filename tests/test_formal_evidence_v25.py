"""Archive-integrity fixtures, not simulator evidence."""
import hashlib
import io
import json
import tarfile
import pytest


@pytest.mark.parametrize('name',['../escape.json','/absolute.json','a/../../escape.json','a\\escape.json'])
def test_archive_paths_cannot_escape_or_change_platform_meaning(tmp_path,name):
    from workflows.formal_evidence_v25 import unpack_verified
    archive=tmp_path/'bad.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        data=b'{}';item=tarfile.TarInfo(name);item.size=len(data);tar.addfile(item,io.BytesIO(data))
    with pytest.raises(ValueError,match='formal_archive_'):
        unpack_verified(archive,tmp_path/'raw',hashlib.sha256(archive.read_bytes()).hexdigest())
    assert not (tmp_path/'raw').exists()


def test_raw_recheck_rejects_mutation_missing_and_extra_files(tmp_path):
    from workflows.formal_evidence_v25 import verify_raw
    raw=tmp_path/'raw';raw.mkdir();payload=b'actual recorded bytes';(raw/'trace.json').write_bytes(payload)
    inventory={'files':{'trace.json':{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}}}
    (raw/'inventory.json').write_text(json.dumps(inventory));verify_raw(raw,inventory)
    (raw/'trace.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='formal_raw_'):verify_raw(raw,inventory)
    (raw/'trace.json').write_bytes(payload);(raw/'extra.json').write_text('{}')
    with pytest.raises(ValueError,match='formal_raw_'):verify_raw(raw,inventory)


def test_wrong_archive_hash_is_rejected_before_output(tmp_path):
    from workflows.formal_evidence_v25 import unpack_verified
    archive=tmp_path/'archive';archive.write_bytes(b'not the approved archive')
    with pytest.raises(ValueError,match='formal_archive_hash'):
        unpack_verified(archive,tmp_path/'raw','0'*64)
    assert not (tmp_path/'raw').exists()
