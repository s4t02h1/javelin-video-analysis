from typing import Optional, Sequence
import math

class SmartSkipper:
    """Simple motion-based frame skipper.
    - pos_thresh: squared pixel distance threshold across key landmarks
    - min_keep: never skip next min_keep frames after an infer
    - max_skip: at most skip this many frames consecutively
    """
    def __init__(self, pos_thresh: float = 6.0, min_keep: int = 1, max_skip: int = 4):
        self.pos_thresh = pos_thresh
        self.min_keep = min_keep
        self.max_skip = max_skip
        self._cooldown = 0
        self._skipped = 0
        self._prev: Optional[Sequence[Optional[tuple[float, float]]]] = None

    def _score(self, landmarks: Optional[Sequence[Optional[tuple[float, float]]]]) -> float:
        if not landmarks or all(p is None for p in landmarks):
            return math.inf  # force infer if nothing
        if self._prev is None:
            return math.inf
        total = 0.0
        count = 0
        # sample subset (every 3rd point) to reduce cost
        for i, p in enumerate(landmarks):
            if i % 3 != 0:
                continue
            q = self._prev[i] if i < len(self._prev) else None
            if p is None or q is None:
                continue
            dx = (p[0] - q[0])
            dy = (p[1] - q[1])
            total += dx * dx + dy * dy
            count += 1
        return total / max(count, 1)

    def should_infer(self, landmarks: Optional[Sequence[Optional[tuple[float, float]]]]) -> bool:
        # cooldown period forces keeping frames
        if self._cooldown > 0:
            self._cooldown -= 1
            self._prev = landmarks
            return True

        score = self._score(landmarks)
        if score >= self.pos_thresh or self._skipped >= self.max_skip:
            # infer now, start cooldown
            self._cooldown = self.min_keep
            self._skipped = 0
            self._prev = landmarks
            return True
        else:
            # skip
            self._skipped += 1
            self._prev = landmarks
            return False
