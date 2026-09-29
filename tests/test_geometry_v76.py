import itertools
import numpy as np
import pytest
from workflows.geometry_v76 import ground_top


def test_ground_uses_actual_top_and_rejects_tilt_or_small_floor():
    points=np.array(list(itertools.product((-50.,50.),(-50.,50.),(-.1,0.))))
    assert ground_top(points)==0
    for bad in (points+[0,0,.01],points*[.01,.01,1],points+np.c_[np.zeros((8,2)),.01*points[:,0]]):
        with pytest.raises(ValueError):ground_top(bad)
