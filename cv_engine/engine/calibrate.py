import cv2
import numpy as np
import json
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="Football Camera Homography Calibration Tool")
    parser.add_argument("--video", type=str, default="cv_engine/test_data/clip_3min.mp4", help="Path to video file")
    parser.add_argument("--output", type=str, default="cv_engine/engine/calibration_config.json", help="Path to save configuration")
    parser.add_argument("--default", action="store_true", help="Generate default calibration without GUI prompt")
    parser.add_argument(
        "--points",
        type=str,
        default=None,
        help=(
            "Non-interactive calibration. Semicolon-separated correspondences of the form "
            "'px,py:pitch_x,pitch_y', at least 4. Example: "
            "'323,177:52.5,0; 323,290:52.5,68; 248,230:43.35,34; 398,230:61.65,34'. "
            "Use this when no GUI is available, or to script a calibration you have already measured."
        ),
    )
    args = parser.parse_args()

    # Non-interactive path takes precedence over both the GUI and --default.
    if args.points:
        pixel_points, pitch_points = parse_points(args.points)
        if len(pixel_points) < 4:
            print(f"[Calibrate] --points supplied only {len(pixel_points)} correspondences; 4 are required.")
            return
        write_config(pixel_points, pitch_points, args.output)
        return

    # Default mapping based on the original trapezoid to standard 105x68 pitch
    default_pixels = [
        [110, 1035],   # Bottom Left
        [265, 275],    # Top Left
        [910, 260],    # Top Right
        [1614, 950]    # Bottom Right
    ]
    default_pitch = [
        [0.0, 68.0],   # Bottom Left (0, 68)
        [0.0, 0.0],    # Top Left (0, 0)
        [105.0, 0.0],  # Top Right (105, 0)
        [105.0, 68.0]  # Bottom Right (105, 68)
    ]

    # Resolve paths relative to repo root if they are not found directly
    video_path = args.video
    if not os.path.exists(video_path):
        alt_video = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_data", "clip_3min.mp4")
        if os.path.exists(alt_video):
            video_path = alt_video

    # Check if we should just write the default config directly
    if args.default or not os.path.exists(video_path):
        print("[Calibrate] Creating default calibration configuration (105m x 68m mapping)...")
        write_config(default_pixels, default_pitch, args.output)
        return

    # Try opening the video to extract first frame
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[Calibrate] Error: Could not open video file {video_path}. Creating default config.")
        write_config(default_pixels, default_pitch, args.output)
        return

    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("[Calibrate] Error: Could not read first frame. Creating default config.")
        write_config(default_pixels, default_pitch, args.output)
        return

    # Interactive click-to-calibrate mode
    pixel_points = []
    pitch_points = []
    
    print("\n=======================================================")
    # Try displaying window to check if GUI is available
    try:
        cv2.namedWindow("Calibration")
    except Exception:
        print("[Calibrate] GUI not available in this shell environment. Creating default config.")
        write_config(default_pixels, default_pitch, args.output)
        return

    def click_event(event, x, y, flags, params):
        if event == cv2.EVENT_LBUTTONDOWN:
            print(f"\nClicked pixel coordinate: ({x}, {y})")
            cv2.circle(frame, (x, y), 5, (0, 0, 255), -1)
            cv2.imshow("Calibration", frame)
            
            # Prompt user for pitch coordinates in console
            try:
                px = float(input("Enter corresponding pitch X coordinate (0 to 105 meters): "))
                py = float(input("Enter corresponding pitch Y coordinate (0 to 68 meters): "))
                pixel_points.append([x, y])
                pitch_points.append([px, py])
                print(f"Mapped ({x}, {y}) -> ({px}m, {py}m)")
            except ValueError:
                print("Invalid numeric coordinates. Click again.")

    cv2.imshow("Calibration", frame)
    cv2.setMouseCallback("Calibration", click_event)
    
    print("INSTRUCTIONS:")
    print("1. Click a landmark on the pitch in the window.")
    print("2. Enter its real-world coordinates in the terminal.")
    print("3. Repeat for at least 4 points (e.g. 4 corners of the pitch).")
    print("4. Press any key on the image window to complete calibration and save.")
    print("=======================================================\n")
    
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if len(pixel_points) < 4:
        print(f"[Calibrate] You only selected {len(pixel_points)} points. At least 4 points are required.")
        print("Creating default config instead.")
        write_config(default_pixels, default_pitch, args.output)
    else:
        write_config(pixel_points, pitch_points, args.output)

def parse_points(spec):
    """
    Parse a --points specification into (pixel_points, pitch_points).
    Format: 'px,py:pitch_x,pitch_y' entries separated by ';'.
    """
    pixel_points, pitch_points = [], []
    for entry in spec.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        try:
            pixel_part, pitch_part = entry.split(":")
            px, py = (float(v) for v in pixel_part.split(","))
            gx, gy = (float(v) for v in pitch_part.split(","))
        except ValueError:
            raise SystemExit(
                f"[Calibrate] Could not parse correspondence '{entry}'. "
                "Expected 'px,py:pitch_x,pitch_y'."
            )
        pixel_points.append([px, py])
        pitch_points.append([gx, gy])
    return pixel_points, pitch_points


def write_config(pixel_pts, pitch_pts, output_path):
    pixel_arr = np.array(pixel_pts, dtype=np.float32)
    pitch_arr = np.array(pitch_pts, dtype=np.float32)
    
    # Calculate Homography Matrix
    H, _ = cv2.findHomography(pixel_arr, pitch_arr)
    
    config = {
        "pixel_vertices": pixel_pts,
        "pitch_vertices": pitch_pts,
        "homography_matrix": H.tolist(),
        # Map a specific track ID to a team, for cases the jersey-colour classifier gets wrong
        # (goalkeepers especially, since their kit matches neither outfield team). Left empty by
        # default: a placeholder ID here would silently mislabel whichever player it lands on.
        "gk_overrides": {}
    }
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(config, f, indent=4)
        
    print(f"[Calibrate] Saved calibration matrix to: {output_path}")

if __name__ == "__main__":
    main()
