import os
import sys
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Set Python path to ensure module importing works
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cv_engine.engine.extractor import CoordinatesExtractor

def draw_pitch(ax):
    """
    Draw a standard 105m x 68m football pitch on the given matplotlib axis.
    """
    # Pitch color
    ax.set_facecolor('#22543d') # Premium forest green
    
    # Boundary Line (105m x 68m)
    pitch_outline = patches.Rectangle((0, 0), 105, 68, edgecolor="white", facecolor="none", linewidth=2)
    ax.add_patch(pitch_outline)
    
    # Center Line
    ax.plot([52.5, 52.5], [0, 68], color="white", linewidth=2)
    
    # Center Circle (Radius 9.15m)
    center_circle = patches.Circle((52.5, 34), 9.15, edgecolor="white", facecolor="none", linewidth=2)
    ax.add_patch(center_circle)
    
    # Center Spot
    center_spot = patches.Circle((52.5, 34), 0.5, color="white")
    ax.add_patch(center_spot)
    
    # Left Penalty Area (16.5m deep, 40.3m wide, centered on Y=34)
    left_penalty = patches.Rectangle((0, 13.85), 16.5, 40.3, edgecolor="white", facecolor="none", linewidth=2)
    ax.add_patch(left_penalty)
    
    # Left Goal Area (5.5m deep, 18.32m wide, centered on Y=34)
    left_goal = patches.Rectangle((0, 24.84), 5.5, 18.32, edgecolor="white", facecolor="none", linewidth=2)
    ax.add_patch(left_goal)
    
    # Right Penalty Area
    right_penalty = patches.Rectangle((88.5, 13.85), 16.5, 40.3, edgecolor="white", facecolor="none", linewidth=2)
    ax.add_patch(right_penalty)
    
    # Right Goal Area
    right_goal = patches.Rectangle((99.5, 24.84), 5.5, 18.32, edgecolor="white", facecolor="none", linewidth=2)
    ax.add_patch(right_goal)
    
    # Set display properties
    ax.set_xlim(-5, 110)
    ax.set_ylim(-5, 73)
    ax.set_aspect('equal')
    ax.set_title("Football Tracking Data Visualizer", color="black", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Pitch Length (meters)", fontsize=10)
    ax.set_ylabel("Pitch Width (meters)", fontsize=10)

def main():
    video_path = "cv_engine/test_data/clip_3min.mp4"
    config_path = "cv_engine/engine/calibration_config.json"
    output_dir = "cv_engine/output"

    # Resolve paths relative to root of cv_engine
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(video_path):
        video_path = os.path.join(base_dir, "test_data", "clip_3min.mp4")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "engine", "calibration_config.json")
    if not os.path.exists(output_dir):
        output_dir = os.path.join(base_dir, "output")
        
    os.makedirs(output_dir, exist_ok=True)

    print("=======================================================")
    print("           PITCH COORDINATES VISUALIZER                ")
    print("=======================================================")
    print(f"Reading video: {video_path}")
    
    calibration_config = None
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            calibration_config = json.load(f)

    # Initialize Extractor
    extractor = CoordinatesExtractor(warmup_frames=5)
    
    # Collect coordinates for target frames (e.g. frame 0, 10, 20)
    target_frames = [0, 10, 20]
    frame_data = {f: [] for f in target_frames}

    try:
        for batch in extractor.extract_coordinates(video_path, calibration_config):
            for record in batch:
                frame_number = record["frame_number"]
                if frame_number in frame_data:
                    frame_data[frame_number].append(record)
    except Exception as e:
        print(f"Error extracting coordinates: {e}")
        sys.exit(1)

    # Plot each target frame
    for frame_num in target_frames:
        records = frame_data[frame_num]
        if not records:
            print(f"No coordinates found for Frame {frame_num}, skipping plot.")
            continue
            
        fig, ax = plt.subplots(figsize=(12, 8))
        draw_pitch(ax)
        
        # Add frame details as subtitle
        ax.text(52.5, 70, f"Frame {frame_num} Detections", ha='center', fontsize=12, fontweight='semibold')
        
        # Color mapping for different groups
        colors = {
            "team_a": "#3182ce",      # Sleek Blue
            "team_b": "#e53e3e",      # Sleek Red
            "referee": "#ecc94b",     # Yellow
            "ball": "#ffffff",        # White
            "goalkeeper": "#ed64a6"   # Pink for Goalkeeper overrides if any
        }
        
        for rec in records:
            team = rec["team_classification"]
            xp = rec["x_pitch"]
            yp = rec["y_pitch"]
            player_id = rec["player_id"]
            
            # Ensure coordinates are within display boundary representation
            if -5 <= xp <= 110 and -5 <= yp <= 73:
                color = colors.get(team, "#718096") # gray default
                marker_size = 120 if team != "ball" else 60
                marker = 'o' if team != "ball" else '8'
                
                # Plot player/ball dot
                ax.scatter(xp, yp, color=color, s=marker_size, edgecolors="black", linewidths=1.2, zorder=5)
                
                # Label ID (skip for ball)
                if team != "ball":
                    ax.text(xp, yp + 1.2, f"{player_id}", color="white", fontsize=8, fontweight="bold",
                            ha='center', va='center', bbox=dict(facecolor='black', alpha=0.6, boxstyle='round,pad=0.2', edgecolor='none'), zorder=6)
        
        output_file = os.path.join(output_dir, f"pitch_frame_{frame_num}.png")
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[Visualizer] Saved pitch plot for Frame {frame_num} to: {output_file}")
        
    print("\nVisual inspection plots generated successfully! ✅")
    print("=======================================================")

if __name__ == "__main__":
    main()
