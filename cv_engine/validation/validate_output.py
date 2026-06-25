import os
import sys
import json
import numpy as np

# Set Python path to ensure module importing works
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cv_engine.engine.extractor import CoordinatesExtractor

def main():
    video_path = "cv_engine/test_data/clip_3min.mp4"
    config_path = "cv_engine/engine/calibration_config.json"

    # Resolve paths relative to root of cv_engine
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(video_path):
        video_path = os.path.join(base_dir, "test_data", "clip_3min.mp4")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "engine", "calibration_config.json")

    print("=======================================================")
    print("      COORDINATES OUTPUT BOUNDS VALIDATION             ")
    print("=======================================================")
    print(f"Loading video: {video_path}")
    print(f"Loading calibration: {config_path if os.path.exists(config_path) else 'Default'}")

    calibration_config = None
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            calibration_config = json.load(f)

    # Initialize Extractor
    extractor = CoordinatesExtractor(warmup_frames=10) # short warmup for short test clip
    
    total_frames = 0
    total_coordinates = 0
    out_of_bounds_count = 0
    out_of_bounds_records = []
    
    x_min, x_max = float('inf'), float('-inf')
    y_min, y_max = float('inf'), float('-inf')
    
    class_counts = {}

    try:
        # Run generator
        for batch in extractor.extract_coordinates(video_path, calibration_config):
            total_coordinates += len(batch)
            for record in batch:
                frame_number = record["frame_number"]
                total_frames = max(total_frames, frame_number + 1)
                
                team = record["team_classification"]
                class_counts[team] = class_counts.get(team, 0) + 1
                
                xp = record["x_pitch"]
                yp = record["y_pitch"]
                
                x_min, x_max = min(x_min, xp), max(x_max, xp)
                y_min, y_max = min(y_min, yp), max(y_max, yp)
                
                # Check Bounds: X: [0, 105], Y: [0, 68]
                is_oob = False
                if not (0.0 <= xp <= 105.0):
                    is_oob = True
                if not (0.0 <= yp <= 68.0):
                    is_oob = True
                    
                if is_oob:
                    out_of_bounds_count += 1
                    if len(out_of_bounds_records) < 10: # Collect up to 10 samples for debugging
                        out_of_bounds_records.append(record)
    except Exception as e:
        print(f"\n[Validation] Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n------------------- SUMMARY -------------------")
    print(f"Total Frames Processed: {total_frames}")
    print(f"Total Coordinates Generated: {total_coordinates}")
    print(f"Detections by Class/Team: {class_counts}")
    
    if total_coordinates > 0:
        oob_percentage = (out_of_bounds_count / total_coordinates) * 100
        print(f"Out-of-Bounds Detections: {out_of_bounds_count} ({oob_percentage:.2f}%)")
        print(f"Pitch Coordinate Ranges:")
        print(f"  X (Pitch Length): [{x_min:.2f}m, {x_max:.2f}m] (Target: [0.0m, 105.0m])")
        print(f"  Y (Pitch Width) : [{y_min:.2f}m, {y_max:.2f}m] (Target: [0.0m, 68.0m])")

        if len(out_of_bounds_records) > 0:
            print("\nFirst few Out-of-Bounds sample records:")
            for idx, rec in enumerate(out_of_bounds_records):
                print(f"  [{idx}] Frame {rec['frame_number']}, ID {rec['player_id']} ({rec['team_classification']}): "
                      f"Pixel ({rec['x_pixel']:.1f}, {rec['y_pixel']:.1f}) -> Pitch ({rec['x_pitch']:.2f}m, {rec['y_pitch']:.2f}m)")

        if oob_percentage > 1.0:
            print("\n[WARNING] More than 1% of coordinates are out of bounds (> 1.0%).")
            print("This usually means players walked outside the calibrated camera polygon bounds.")
        else:
            print("\n[SUCCESS] Coordinate validation bounds checks passed! (Under 1% out of bounds).")
    else:
        print("\n[ERROR] No coordinate data was extracted.")
        sys.exit(1)
        
    print("=======================================================")

if __name__ == "__main__":
    main()
