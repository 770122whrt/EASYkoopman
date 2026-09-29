"""Relocate and verify immutable approved runtime assets without old experiment code.

The fixed handoff is the trust root. All frozen source, model, input/approval and
fit-cache bytes are verified before reconstructing the unchanged support domains.
No legacy prediction evaluation or controller factory executes while loading.
"""
from dataclasses import dataclass
import hashlib,json,re
from pathlib import Path,PurePosixPath
from koopman.support_domain import load_fit_domains
from koopman.physics_context import PhysicalContext

HANDOFF_SHA256='5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'
HANDOFF_DIR='docs/evidence/phase8_4/server-projected-formal-v38-r23'
HANDOFF_FILE=HANDOFF_DIR+'/prediction-control-handoff-v2.json'
FIT_DIR='docs/evidence/phase8_4/identification-fit-20260913-r17'
FIT_ACCEPTANCE='docs/evidence/phase8_4/server-identification-20260913-r17/fit/acceptance.json'
# Exact bytes of all original approved r23 inputs, including authorization lineage.
TRUSTED_INPUT_HASHES = {
    "authorization-parent.json": "650b5d3cea5a7301fedd309468edb137be1b0f66e16de45c5337d9063c68a68f",
    "authorization.json": "fd1f7be7cc4464e008ffc687b0da1569d2ff09a125d4d5da42e9528e65a45359",
    "budget.json": "b632e77b77b5ac5a5c34621030a032e7cd4546801978f4433fdaeae5710c4829",
    "evaluation-policy.json": "acedf309fc035771bf7d9f5f5c49a5d5b4eb5781204e535e76421aa5a05180e7",
    "freeze.json": "6a6274f9466894871621148573dac6a2fb366cd63442b28a52cac36d29ad37a4",
    "historical-budget.json": "92b4958582b62aea3f3cdeb294952a8cb892da1e7679098ee45af86d9fa685be",
    "local-readiness.json": "b005513b5c862bd17977e98aef65417d7e9e88069d8b43d3d0ed58987dc9ab78",
    "model-manifest.json": "393ccbfd80ab1878ff23d78bb1ebefe3cc040a0698bd50eb42d965513dd0ca8a",
    "numeric-diagnostics.json": "e7663cd60b7f477bfcadddb3f43a8cf3ded0f5fce0a235a40ddcbe5372f8292f",
    "numeric-recovery.json": "2ef4109631947fd5d65eb8098ef16dc55215501180d65060956d14488a9d6cb5",
    "parent-budget.json": "76d906daa7188284042fdd56344651caff85754c92a5c985b2f58c9516998d6b",
    "parent-freeze.json": "a592b69b84e3d6a2fad0b0cc70d3613f44a23c077ac8f0a33bead61e156effa5",
    "parent-preflight-audit.json": "effe92dc081776d66a7cd724eb49d45eb9be944b2957b53fc43e7fbffa5eda20",
    "parent-validation-audit.json": "1a5aaa47b7e9cb43697cf31a5f60533f167f6545ef42befa8c3787f3b3769dc8",
    "policy.json": "e03a42997379176e96b420c69671119f17ecd74244a0a756ceeb3bf502f28f7a",
    "protocol.json": "c50853b1d3d7625e06a09d502f3df8082af993e74d0ea7a17e6156e94450ce4b",
    "resource-amendment.json": "f070af5f4a6279500804bfa30b55d296e79a0887f340c75276749e85b437ef93",
    "resource-approval.json": "7450a86029e94691a7e409d8d3268fb87dc6569e57c2674b9e8d56ba293f880b",
    "resource-parent-authorization.json": "365509fe7a633ad00d7b1775947276f156c431a66c43fdc1e1c5df63d9e0ea04",
    "resource-parent-budget.json": "40824fa2c3070bc4343dea11a435c6e0fe332600a11817cf2f2571fd1df03d16",
    "resource-parent-freeze.json": "b52e81b2e9f3ad95282ff7041b5b316ce14b3270a539d917e0102376e6474657",
    "validation-analysis-audit.json": "70bfc08364b0b53d3dd0c3fe3449c10c9ccf5a1d1e8c7cea4da59f6946cccde5",
    "validation-numeric-diagnostics.json": "d391648426fa30c34a3288be58c76f7333409faa7f8698774a396a3fbc7c33f7",
    "validation-numeric-recovery.json": "b4b7ed380720abf21a4af0a46832987c0018eaea7caf7db7b1eeb5948f287531",
    "validation-parent-budget.json": "463888c16e3200fc4d5d8486cc13fd5358820988b6174618bfeca61d469c0b7d",
    "validation-pullback.json": "1a5aaa47b7e9cb43697cf31a5f60533f167f6545ef42befa8c3787f3b3769dc8"
}

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



def verify_frozen_bundle(root, inputs, handoff):
    for name,digest in TRUSTED_INPUT_HASHES.items():
        if sha(confined(inputs,name))!=digest:
            raise ValueError('assets_frozen_input:'+name)
    frozen=read(inputs/'freeze.json')
    if (frozen.get('source_commit')!=handoff['source_commit'] or frozen.get('model_fits')!=0
            or frozen.get('model_handoff') is not False):
        raise ValueError('assets_frozen_source_identity')
    manifest=read(root/'SOURCE_MANIFEST.json')
    files=manifest['files_sha256']
    if not files or not {FIT_DIR+'/cache-inventory.json',FIT_ACCEPTANCE}<=set(files):
        raise ValueError('assets_source_inventory')
    for name,digest in files.items():
        if not re.fullmatch('[0-9a-f]{64}',digest) or sha(confined(root,name))!=digest:
            raise ValueError('assets_source_hash:'+name)
    return frozen

def load_assets(location, *, model_key):
    if not isinstance(location, AssetLocation):
        raise ValueError('assets_location')
    if location.handoff_sha256!=HANDOFF_SHA256:
        raise ValueError('assets_untrusted_handoff')
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
    verify_frozen_bundle(source, inputs, handoff)
    entry = handoff['eligible_models'][model_key]
    model_path = confined(source, entry['path'])
    if sha(model_path) != entry['sha256']:
        raise ValueError('assets_model_hash')
    inventory_path=root/FIT_DIR/'cache-inventory.json'
    source_inventory=read(source/'SOURCE_MANIFEST.json')['files_sha256']
    if sha(inventory_path)!=source_inventory[FIT_DIR+'/cache-inventory.json'] or sha(root/FIT_ACCEPTANCE)!=source_inventory[FIT_ACCEPTANCE]:
        raise ValueError('assets_cache_identity')
    domains = load_fit_domains(root, model_path)
    if set(domains) != set(entry['training_configurations']):
        raise ValueError('assets_training_configuration_binding')
    return LoadedAssets(location, handoff, model_key, model_path, entry['sha256'], domains)


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
