import os
import sys
import unittest

# Ensure modules are importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cv_engine.engine.extractor import CoordinatesExtractor

class TestCoordinatesExtractor(unittest.TestCase):
    def setUp(self):
        self.video_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_data", "clip_3min.mp4")
        self.extractor = CoordinatesExtractor(warmup_frames=5)

    def test_extract_coordinates_structure(self):
        """
        Verify that extract_coordinates yields batches with the correct format,
        types, and coordinates bounds constraints.
        """
        self.assertTrue(os.path.exists(self.video_path), f"Test clip not found at: {self.video_path}")
        
        batches = list(self.extractor.extract_coordinates(self.video_path))
        
        # Check that we got at least one batch
        self.assertGreater(len(batches), 0, "No coordinate batches were yielded by the extractor")
        
        for batch in batches:
            self.assertIsInstance(batch, list)
            self.assertGreater(len(batch), 0, "Batch is empty")
            
            for record in batch:
                self.assertIsInstance(record, dict)
                
                # Assert required keys are present
                self.assertIn("frame_number", record)
                self.assertIn("player_id", record)
                self.assertIn("team_classification", record)
                self.assertIn("x_pixel", record)
                self.assertIn("y_pixel", record)
                self.assertIn("x_pitch", record)
                self.assertIn("y_pitch", record)
                
                # Check data types
                self.assertIsInstance(record["frame_number"], int)
                self.assertIsInstance(record["player_id"], int)
                self.assertIsInstance(record["team_classification"], str)
                self.assertIsInstance(record["x_pixel"], float)
                self.assertIsInstance(record["y_pixel"], float)
                self.assertIsInstance(record["x_pitch"], float)
                self.assertIsInstance(record["y_pitch"], float)
                
                # Check value constraints
                self.assertGreaterEqual(record["frame_number"], 0)
                self.assertIn(record["team_classification"], ["team_a", "team_b", "referee", "ball"])
                
                # Assert coordinates are within boundaries: X [0, 105], Y [0, 68]
                self.assertGreaterEqual(record["x_pitch"], 0.0)
                self.assertLessEqual(record["x_pitch"], 105.0)
                self.assertGreaterEqual(record["y_pitch"], 0.0)
                self.assertLessEqual(record["y_pitch"], 68.0)

if __name__ == "__main__":
    unittest.main()
