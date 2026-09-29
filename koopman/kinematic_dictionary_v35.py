"""State-projected controlled observables with an explicit rotation-rate basis.

The readout is62x16, not an autonomous62-dimensional linear state transition.
Only the dictionary changes relative to the v34 state-projection candidate.
"""
from dataclasses import dataclass
import numpy as np
from koopman.sparse_world_edmd_v30 import lift as parent_lift,feature_names as parent_names
from koopman.projected_edmd_v24 import rotation
from koopman.physical_terms_v26 import validate_states
from koopman.controlled_lift_v33 import full_step_input_effect
from workflows.sparse_evaluation_v32 import decode_lift


def feature_names():return parent_names('nonlinear')+[f'rotation_rate_{i}_{j}' for i in range(3) for j in range(3)]


def lift(states,context):
    x=validate_states(states);omega=x[:,8:];skew=np.zeros((len(x),3,3))
    skew[:,0,1]=-omega[:,2];skew[:,0,2]=omega[:,1];skew[:,1,0]=omega[:,2]
    skew[:,1,2]=-omega[:,0];skew[:,2,0]=-omega[:,1];skew[:,2,1]=omega[:,0]
    return np.c_[parent_lift(x,context,'nonlinear'),(rotation(x[:,1:5])@skew).reshape(len(x),9)]


def projected_step(states,acceleration,context,reference,matrix):
    z=lift(states,context);K=np.asarray(matrix,dtype=float)
    if K.shape!=(62,16) or not np.isfinite(K).all() or reference.family!='nonlinear':raise ValueError('kinematic_readout_matrix')
    following=z@K+full_step_input_effect(states,acceleration,context,reference)[:,:16]
    try:return decode_lift(following)
    except np.linalg.LinAlgError as exc:raise ValueError('kinematic_readout_svd') from exc


@dataclass(frozen=True)
class KinematicModel:
    matrix:np.ndarray
    reference:object

    def __call__(self,states,acceleration,context):
        return projected_step(states,acceleration,context,self.reference,self.matrix)
