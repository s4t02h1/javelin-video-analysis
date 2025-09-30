import unittest
import numpy as np
import cv2
from src.pipelines.acceleration_heatmap import calculate_acceleration_heatmap

class TestAccelerationHeatmap(unittest.TestCase):

    def setUp(self):
        # Sample speed data for testing
        self.speed_data = np.array([0, 10, 20, 30, 40, 50, 60])
        self.expected_heatmap_shape = (len(self.speed_data), len(self.speed_data))

    def test_calculate_acceleration_heatmap(self):
        # Calculate the acceleration heatmap
        heatmap = calculate_acceleration_heatmap(self.speed_data)

        # Check if the heatmap has the expected shape
        self.assertEqual(heatmap.shape, self.expected_heatmap_shape)

        # Check if the heatmap values are non-negative
        self.assertTrue(np.all(heatmap >= 0))

if __name__ == '__main__':
    unittest.main()