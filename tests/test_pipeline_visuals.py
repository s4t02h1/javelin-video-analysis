import numpy as np
from jva_visuals.registry import VisualPassRegistry

def test_registry_build_and_apply():
    passes = VisualPassRegistry.build_from_config({"wrist_trail": True, "vectors": True, "heatmap": True, "hud": True})
    assert len(passes) == 4
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    state = {"points": [(10,10)]*33, "fps": 30.0, "velocities": [(0.0,0.0)]*33}
    out = VisualPassRegistry.apply_all(frame, state, passes)
    assert out.shape == frame.shape