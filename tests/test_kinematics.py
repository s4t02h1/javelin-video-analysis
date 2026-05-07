import numpy as np
from jva_visuals.kinematics import KinematicsHelper

def test_constant_motion_accel_zero():
    kin = KinematicsHelper()
    pts0 = np.zeros((33, 2), dtype=np.float32)
    kin.update(pts0, 1/30)
    pts1 = np.zeros((33, 2), dtype=np.float32)
    res = kin.update(pts1, 1/30)
    a = res["acc"]
    assert np.all(np.isfinite(a[np.isfinite(a)]))