import numpy as np
from workflows.forecast_diagnostics_v73 import matching_predictions


def test_stop_comparison_at_first_actual_command_change():
    commands=np.zeros((4,4),dtype=np.float32)
    rows=[dict(command=dict(telemetry=dict(virtual_control_4=[[0.,0.,0.,0.]])),state_after_physics_11=[np.r_[5.5,1.,np.zeros(9)].tolist()]) for _ in range(8)]
    rows[3]['command']['telemetry']['virtual_control_4'][0][1]=.01
    payload=dict(metadata=dict(history_physics_index=0),commands=commands,predictions=np.zeros((8,11)))
    p,a=matching_predictions(dict(substeps=rows),payload)
    assert p.shape==a.shape==(3,11)
