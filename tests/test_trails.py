import numpy as np
from jva_visuals.trails import WristTrailPass

def test_trail_apply_runs():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    state = {"points": [None]*33}
    state["points"][16] = (50, 50)
    out = WristTrailPass({"maxlen": 5}).apply(frame, state)
    assert out.shape == frame.shape