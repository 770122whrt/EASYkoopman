"""Controlled EDMD state readout followed by explicit consistent re-lifting.

Learned height and rotation outputs are used. This is not the v30 analytic-pose
predictor, an unprojected53D recurrence, or a constant-A/B control model.
"""
from dataclasses import dataclass
import re
import numpy as np
from koopman.sparse_world_edmd_v30 import lift
from koopman.controlled_lift_v33 import full_step_input_effect
from koopman.projected_edmd_v24 import _readonly
from workflows.sparse_evaluation_v32 import decode_lift
from workflows.identify_sparse_world_v30 import from_record as read_parent,validate_matrix


def projected_step(states,acceleration,context,reference,matrix):
    # A new lift from the CURRENT predicted state is intentional at every call.
    z=lift(states,context,reference.family);A=np.asarray(matrix,dtype=float)
    if A.shape!=(z.shape[1],z.shape[1]) or not np.isfinite(A).all():raise ValueError('state_projection_matrix')
    following=z@A+full_step_input_effect(states,acceleration,context,reference)
    try:return decode_lift(following)
    except np.linalg.LinAlgError as exc:raise ValueError('state_projection_readout_svd') from exc


@dataclass(frozen=True)
class StateProjectedModel:
    matrix:np.ndarray
    reference:object

    def __call__(self,states,acceleration,context):
        return projected_step(states,acceleration,context,self.reference,self.matrix)


def from_record(record,parent,parent_sha256):
    reference=read_parent(parent)
    if (record.get('schema')!='controlled-lift-input-v33' or not re.fullmatch('[0-9a-f]{64}',parent_sha256)
        or record.get('parent_sha256')!=parent_sha256 or record.get('parent_model_id')!=parent.get('model_id')
        or any(record.get(k)!=parent.get(k) for k in ('family','feature_names','configurations','fit_source','fit_episode_hashes','damping','quadratic','angular_damping'))
        or record.get('audit',{}).get('training_role')!='fit' or record.get('audit',{}).get('new_velocity_parameter_fits')!=0):
        raise ValueError('state_projection_parent_binding')
    matrix=validate_matrix(record['matrix'],reference.family,reference.damping,reference.quadratic,reference.angular_damping)
    return StateProjectedModel(_readonly(matrix),reference)
