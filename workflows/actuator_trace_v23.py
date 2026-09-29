"""Annotate copied trace rows with causal estimates; never feed oracle truth back."""
import numpy as np
from workflows.control_seam_v23 import estimate_speed


def annotate_estimates(rows, previous, *, tau):
    estimate=np.array(previous,dtype=float,copy=True)
    for row in rows:
        pwm=row['command']['telemetry']['motor_pwm_n'][0]
        estimate=estimate_speed(estimate,pwm,tau=tau,dt=row['physics_dt_s'])
        row['causal_speed_estimate_n']=[estimate.tolist()]
        # Truth is used only after prediction for diagnostic error reporting.
        actual=np.asarray(row['command']['actuator_speed_n'][0],dtype=float)
        if actual.shape!=estimate.shape or not np.isfinite(actual).all():
            raise ValueError('trace_actuator_truth_invalid')
        row['estimated_minus_actual_speed_n']=[(estimate-actual).tolist()]
    return estimate
