"""Package the current dependency closure and frozen experiment artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

from workflows.disturbance_protocol import get_protocol
from workflows.disturbance_data import (
    ROOT, PHYSICAL_SHA256, MODEL_SHA256, frozen_physics, frozen_model, verify_manifest,
)
from workflows import source_freeze


def prepare(output, *, version="v88"):
    spec = get_protocol(version)
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    frozen_physics()
    frozen_model()
    paths = source_freeze.source_paths()
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
    manifest = dict(
        schema="current-source-freeze", protocol=spec.protocol(),
        physical_sha256=PHYSICAL_SHA256, model_sha256=MODEL_SHA256,
        git_base=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        files=files,
    )
    output.mkdir(parents=True, exist_ok=False)
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    verify_manifest(path, spec=spec)
    with tarfile.open(output / "source.tar.gz", "w:gz") as archive:
        for name in paths:
            archive.add(ROOT / name, arcname=name, recursive=False)
        archive.add(path, arcname="current-manifest.json", recursive=False)
    result = source_freeze.verify(path, source_archive=output / "source.tar.gz")
    return dict(files=len(paths), manifest_sha256=result["source_manifest_sha256"],
                bundle_sha256=result["source_archive_sha256"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", choices=("v86", "v87", "v88"), default="v88")
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, version=args.version)), flush=True)


if __name__ == "__main__":
    main()
