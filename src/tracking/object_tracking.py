import cv2

class ObjectTracker:
    def __init__(self, tracker_type='CSRT'):
        self.tracker_type = tracker_type
        self.tracker = self.create_tracker()

    def create_tracker(self):
        if self.tracker_type == 'CSRT':
            return cv2.TrackerCSRT_create()
        elif self.tracker_type == 'KCF':
            return cv2.TrackerKCF_create()
        elif self.tracker_type == 'MIL':
            return cv2.TrackerMIL_create()
        else:
            raise ValueError("Unsupported tracker type. Choose 'CSRT', 'KCF', or 'MIL'.")

    def initialize(self, frame, bbox):
        self.tracker.init(frame, bbox)

    def update(self, frame):
        success, bbox = self.tracker.update(frame)
        return success, bbox

    def draw_bbox(self, frame, bbox):
        (x, y, w, h) = [int(v) for v in bbox]
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2, 1)