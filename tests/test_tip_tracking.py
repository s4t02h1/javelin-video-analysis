import unittest
from src.pipelines.tip_tracking import track_javelin_tip
from src.tracking.marker_based import marker_based_tracking
from src.tracking.object_tracking import object_tracking

class TestTipTracking(unittest.TestCase):

    def setUp(self):
        self.video_path = "data/input/test_video.mp4"
        self.expected_output_path = "data/output/test_output.mp4"

    def test_marker_based_tracking(self):
        result = marker_based_tracking(self.video_path)
        self.assertIsNotNone(result)
        self.assertTrue(len(result) > 0)

    def test_object_tracking(self):
        result = object_tracking(self.video_path)
        self.assertIsNotNone(result)
        self.assertTrue(len(result) > 0)

    def test_track_javelin_tip(self):
        result = track_javelin_tip(self.video_path)
        self.assertIsNotNone(result)
        self.assertTrue(len(result) > 0)

if __name__ == "__main__":
    unittest.main()