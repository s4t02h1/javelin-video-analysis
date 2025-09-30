import unittest
from src.pipelines.speed_visualization import visualize_speed
import cv2
import numpy as np

class TestSpeedVisualization(unittest.TestCase):

    def setUp(self):
        # Sample frame for testing
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.speed_data = np.array([0, 10, 20, 30, 40, 50])  # Example speed data
        self.color_ranges = {
            'low': (0, 0, 255),    # Red for low speed
            'medium': (0, 255, 255),  # Yellow for medium speed
            'high': (0, 255, 0)    # Green for high speed
        }

    def test_visualize_speed(self):
        # Test the speed visualization function
        output_frame = visualize_speed(self.frame, self.speed_data, self.color_ranges)
        
        # Check if the output frame has the same shape as the input frame
        self.assertEqual(output_frame.shape, self.frame.shape)

        # Check if the output frame is not the same as the input frame
        self.assertFalse(np.array_equal(output_frame, self.frame))

    def test_color_mapping(self):
        # Test color mapping based on speed
        speed = 25
        expected_color = self.color_ranges['medium']
        mapped_color = visualize_speed.map_speed_to_color(speed, self.color_ranges)
        
        self.assertEqual(mapped_color, expected_color)

if __name__ == '__main__':
    unittest.main()