"""Version-bound adapters to the shared raw-data acceptance implementation."""
from functools import partial
from workflows import protocol_v87 as spec
from workflows.disturbance_data_v86 import ROOT,PHYSICAL_PATH,PHYSICAL_SHA256,context,frozen_physics
from workflows.disturbance_data_v86 import verify_manifest as _verify,load_episode as _load,validate_trace as _validate

verify_manifest=partial(_verify,spec=spec)
load_episode=partial(_load,spec=spec)
validate_trace=partial(_validate,spec=spec)
