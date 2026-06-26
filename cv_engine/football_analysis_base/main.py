from utils import read_video, save_video
from trackers import Tracker
import cv2
from team_assigner import TeamAssigner
from player_ball_assignment import PlayerBallAssigner
import numpy as np
from camera_movement_estimator import CameraMovementEstimator
from view_transformer import ViewTransformer
from speed_and_distance_estimator import SpeedAndDistanceEstimator


def main():

    # Read Video
    video_frames = read_video("input_videos/08fd33_4.mp4")

    # initialize tracker
    tracker = Tracker("models/best.pt")

    tracks = tracker.get_object_tracks(
        video_frames, read_from_stub=True, stub_path="stubs/track_stubs.pkl"
    )

    # Get object Positions
    tracker.add_position_to_tracks(tracks)

    # save copped image of a player
    # for track_id, player_data in tracks["players"][0].items():
    #     bbox = player_data["bbox"]
    #     frame = video_frames[0]

    #     # crop bbox from frame
    #     x1, y1, x2, y2 = map(int, bbox)
    #     cropped_image = frame[y1:y2, x1:x2]

    #     # save the cropped image
    #     cv2.imwrite(f"output_videos/cropped_player_{track_id}.jpg", cropped_image)
    #     break  # only process the first player

    # camera movement estimator
    camera_movement_estimator = CameraMovementEstimator(video_frames[0])
    camera_movement_per_frame = camera_movement_estimator.get_camera_movement(
        video_frames, read_from_stub=True, stub_path="stubs/camera_movement_stub.pkl"
    )
    camera_movement_estimator.add_adjust_positions_to_tracks(
        tracks, camera_movement_per_frame
    )

    # view tranformer
    view_transformer = ViewTransformer()
    view_transformer.add_transformed_positions_to_tracks(tracks)

    # interpolate BAll Positions
    tracks["ball"] = tracker.interpolate_ball_positions(tracks["ball"])

    # Speed and Distance Estimator
    speed_and_distance_estimator = SpeedAndDistanceEstimator()
    speed_and_distance_estimator.add_speed_and_distance_to_tracks(tracks)

    # Assign Player Teams

    team_assigner = TeamAssigner()
    
    # Find the first frame that actually has player detections to initialize team colors
    first_frame_with_players = 0
    for frame_num, player_track in enumerate(tracks["players"]):
        if player_track:
            first_frame_with_players = frame_num
            break
            
    team_assigner.assign_team_color(video_frames[first_frame_with_players], tracks["players"][first_frame_with_players])

    for frame_num, player_track in enumerate(tracks["players"]):
        for player_id, track in player_track.items():
            team = team_assigner.get_player_team(
                video_frames[frame_num], track["bbox"], player_id
            )

            tracks["players"][frame_num][player_id]["team"] = team
            tracks["players"][frame_num][player_id]["team_color"] = (
                team_assigner.team_colors[team]
            )

    # Assign Ball Acquision
    player_assigner = PlayerBallAssigner()
    team_ball_control = []
    for frame_num, player_track in enumerate(tracks["players"]):
        ball_box = tracks["ball"][frame_num][1]["bbox"]
        assigned_player = player_assigner.assign_ball_to_player(player_track, ball_box)

        if assigned_player != -1:
            tracks["players"][frame_num][assigned_player]["has_ball"] = True
            team_ball_control.append(
                tracks["players"][frame_num][assigned_player]["team"]
            )
        else:
            team_ball_control.append(team_ball_control[-1])

    team_ball_control = np.array(team_ball_control)

    # Draw output
    ## Draw Object Tracks
    output_video_frames = tracker.draw_annotations(
        video_frames, tracks, team_ball_control
    )

    # draw camera movement
    output_video_frames = camera_movement_estimator.draw_camera_movement(
        output_video_frames, camera_movement_per_frame
    )

    # Draw speed and Distance
    speed_and_distance_estimator.draw_speed_and_distance(output_video_frames, tracks)

    # Save Video
    save_video(output_video_frames, "output_videos/output_video.avi")


if __name__ == "__main__":
    main()
