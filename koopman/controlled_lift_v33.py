"""Bounded diagnostic of discrete input timing, not a constant-A/B MPC model."""
import numpy as np
from koopman.sparse_world_edmd_v30 import lift,input_effect
from workflows.sparse_evaluation_v32 import decode_lift


def full_step_input_effect(states,acceleration,context,reference):
    """Difference of two causal, same-state, full-step parameter-model outputs."""
    x=np.asarray(states,dtype=float);a=np.asarray(acceleration,dtype=float)
    if a.shape!=(len(x),6) or not np.isfinite(a).all():raise ValueError('controlled_lift_input')
    driven=reference(x,a,context);unforced=reference(x,np.zeros_like(a),context)
    return lift(driven,context,reference.family)-lift(unforced,context,reference.family)


def latent_step(latent,readout,acceleration,context,reference,matrix,input_mode):
    z=np.asarray(latent,dtype=float);a=np.asarray(matrix,dtype=float)
    if a.shape!=(z.shape[1],z.shape[1]):raise ValueError('controlled_lift_matrix_shape')
    if input_mode=='corrected':effect=full_step_input_effect(readout,acceleration,context,reference)
    elif input_mode=='old':effect=input_effect(readout,acceleration,context,reference.family,reference.angular_damping)
    else:raise ValueError('controlled_lift_input_mode')
    following=z@a+effect
    # Readout does not replace the latent recurrence by a re-lifted state.
    return following,decode_lift(following)
