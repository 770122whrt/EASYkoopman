"""Explicit relocation of immutable v38 assets, separate from new run approval.

The historical absolute source directory is preserved as data, never followed
by this loader. Relative locations are supplied by the new release. All frozen
bundle/authorization hashes and fit admission checks still run before READY.
This module neither releases an experiment nor modifies a frozen artifact.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

from koopman.bounded_mpc_v44 import SearchConfig, load_fit_domains
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.projected_edmd_v24 import PhysicalContext


HANDOFF_DIR = 'docs/evidence/phase8_4/server-projected-formal-v38-r23'
HANDOFF_FILE = HANDOFF_DIR + '/prediction-control-handoff-v2.json'
FIT_DIR = 'docs/evidence/phase8_4/identification-fit-20260913-r17'
FIT_ACCEPTANCE = 'docs/evidence/phase8_4/server-identification-20260913-r17/fit/acceptance.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def confined(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
            or PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts):
        raise ValueError('assets_relative_path')
    target = (Path(root)/relative).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError('assets_relative_path_escape')
    return target


@dataclass(frozen=True)
class AssetLocation:
    root: str
    source_relative: str
    inputs_relative: str
    handoff_sha256: str

    def __post_init__(self):
        if not isinstance(self.root, str) or not Path(self.root).is_absolute():
            raise ValueError('assets_root_absolute_required')
        if not isinstance(self.handoff_sha256, str) or not re.fullmatch('[0-9a-f]{64}', self.handoff_sha256):
            raise ValueError('assets_handoff_digest')
        confined(self.root, self.source_relative)
        confined(self.root, self.inputs_relative)


@dataclass(frozen=True)
class PortableWorkerSpec:
    location: AssetLocation
    model_key: str
    model_sha256: str
    configuration: str
    support_id: str
    compiler_directory: object = None
    config: SearchConfig = SearchConfig()
    feedback_config: FeedbackConfig = FeedbackConfig()


@dataclass
class LoadedAssets:
    location: AssetLocation
    handoff: dict
    model_key: str
    model_path: Path
    model_sha256: str
    domains: dict

    def context(self, configuration):
        if configuration not in self.domains:
            raise ValueError('assets_configuration_not_supported')
        key = self.domains[configuration].context_key
        return PhysicalContext(mass=key[0], inertia=key[1:4], cob=key[4:7], volume=key[7],
                               drag_multiplier=key[8], rho=key[9], beta=key[10], gravity=key[11])

    def worker_spec(self, configuration, *, compiler_directory=None,
                    config=SearchConfig(), feedback_config=FeedbackConfig()):
        self.context(configuration)
        return PortableWorkerSpec(self.location, self.model_key, self.model_sha256, configuration,
                                  self.domains[configuration].identity, compiler_directory, config, feedback_config)


def load_assets(location, *, model_key):
    if not isinstance(location, AssetLocation):
        raise ValueError('assets_location')
    root = Path(location.root).resolve()
    handoff_path = root/HANDOFF_FILE
    if sha(handoff_path) != location.handoff_sha256:
        raise ValueError('assets_handoff_hash')
    handoff = read(handoff_path)
    if (handoff.get('schema') != 'projected-v38-prediction-control-interface-handoff-v2'
            or handoff.get('status') != 'qualified_for_bounded_control_integration'
            or handoff.get('prediction_handoff') is not True
            or handoff.get('closed_loop_controller_promoted') is not False
            or model_key not in handoff['eligible_models']):
        raise ValueError('assets_eligible_model')
    if sha(root/HANDOFF_DIR/'formal-closeout.json') != handoff['closeout_sha256']:
        raise ValueError('assets_closeout_hash')
    source = confined(root, location.source_relative)
    inputs = confined(root, location.inputs_relative)
    for path, expected in ((inputs/'freeze.json', handoff['formal_freeze_sha256']),
                           (inputs/'model-manifest.json', handoff['model_manifest_sha256']),
                           (source/'SOURCE_MANIFEST.json', handoff['source_manifest_sha256'])):
        if sha(path) != expected:
            raise ValueError('assets_frozen_binding:' + path.name)
    from workflows.projected_release_v38 import verify_bundle
    verify_bundle(source, inputs, handoff['source_commit'])
    entry = handoff['eligible_models'][model_key]
    model_path = confined(source, entry['path'])
    if sha(model_path) != entry['sha256']:
        raise ValueError('assets_model_hash')
    domains = load_fit_domains(root, model_path)
    if set(domains) != set(entry['training_configurations']):
        raise ValueError('assets_training_configuration_binding')
    return LoadedAssets(location, handoff, model_key, model_path, entry['sha256'], domains)


def portable_model_factory(spec):
    """Verify and warm the same v53 cached solver inside a fresh worker."""
    if not isinstance(spec, PortableWorkerSpec):
        raise ValueError('assets_worker_spec')
    assets = load_assets(spec.location, model_key=spec.model_key)
    domain = assets.domains.get(spec.configuration)
    if domain is None or domain.identity != spec.support_id or assets.model_sha256 != spec.model_sha256:
        raise ValueError('assets_worker_binding')
    if spec.compiler_directory is not None:
        compiler = Path(spec.compiler_directory).resolve()
        if not compiler.is_dir():
            raise ValueError('assets_compiler_missing')
        sys.path.insert(0, str(compiler))
    import numba, llvmlite
    if numba.__version__ != '0.61.2' or llvmlite.__version__ != '0.44.0':
        raise ValueError('assets_compiler_version')
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    from workflows.identify_sparse_world_v30 import from_record
    from koopman.compiled_projected_v43 import prepare_compiled
    from koopman.cached_checks_v53 import CachedRecoverySolver
    context = assets.context(spec.configuration)
    predictor = prepare_compiled(from_record(read(assets.model_path)), context)
    return CachedRecoverySolver(domain, context, predictor, config=spec.config, feedback_config=spec.feedback_config)


def prepare_assets(location, destination, *, maximum_bytes=96*1024**2):
    """Create a fresh asset-only snapshot; no code overlay or experiment launch.

    The v38 source manifest still names its exact unchanged source files. Later
    additive Phase9 modules require a NEW executable-release manifest. Only fit
    cache arrays are copied; historical acceptance/approval metadata is inert.
    """
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('assets_destination_exists')
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise ValueError('assets_size_limit')
    assets = load_assets(location, model_key='nonlinear__pooled')
    source = confined(location.root, location.source_relative)
    inputs = confined(location.root, location.inputs_relative)
    root = Path(location.root)
    files = {rel: confined(source, rel) for rel in read(source/'SOURCE_MANIFEST.json')['files_sha256']}
    files['SOURCE_MANIFEST.json'] = source/'SOURCE_MANIFEST.json'
    for p in inputs.iterdir():
        if not p.is_file() or p.is_symlink():
            raise ValueError('assets_input_inventory')
        files['assets/v38/inputs/'+p.name] = p
    inventory = read(root/FIT_DIR/'cache-inventory.json')
    additions = [HANDOFF_FILE, HANDOFF_DIR+'/formal-closeout.json', FIT_ACCEPTANCE,
                 FIT_DIR+'/cache-inventory.json'] + [FIT_DIR+'/'+name for name in inventory['files_sha256']]
    for rel in additions:
        target = confined(root, rel)
        if rel in files and sha(files[rel]) != sha(target):
            raise ValueError('assets_duplicate_path_conflict')
        files[rel] = target
    size = sum(p.stat().st_size for p in files.values())
    if size > maximum_bytes:
        raise ValueError('assets_size_limit')
    # Failures leave an incomplete new directory for diagnosis, never delete or
    # overwrite an existing destination. Every copied byte is checked again.
    destination.mkdir(parents=True, exist_ok=False)
    copied = {}
    for rel, path in sorted(files.items()):
        payload = path.read_bytes()
        output = confined(destination, rel); output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(payload)
        copied[rel] = hashlib.sha256(payload).hexdigest()
        if sha(output) != copied[rel]:
            raise ValueError('assets_copy_mismatch')
    relocated = AssetLocation(str(destination), '.', 'assets/v38/inputs', location.handoff_sha256)
    admitted = load_assets(relocated, model_key='nonlinear__pooled')
    if any(admitted.domains[k].identity != d.identity for k, d in assets.domains.items()):
        raise ValueError('assets_relocation_changed_support')
    report = dict(schema='phase9-relocated-assets-v56', status='verified_assets_only_not_executable_release',
        frozen_handoff_sha256=location.handoff_sha256, bytes=size, files_sha256=copied,
        source_relative='.', inputs_relative='assets/v38/inputs', new_fits=0, new_server_runs=0,
        support_ids={k: d.identity for k, d in admitted.domains.items()},
        historical_absolute_path_preserved_unused=True, model_sha256=admitted.model_sha256)
    with (destination/'ASSET_RELOCATION.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    return relocated
