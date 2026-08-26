import math
from collections import defaultdict
from django.utils import timezone
from matches.models import Match, TrackingCoordinate, MatchEvent

def distance(x1, y1, x2, y2):
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2)


# ── Plausibility ceilings ────────────────────────────────────────────────────
# Coordinates come from a detector plus a tracker, so a frame-to-frame jump can be an
# artifact rather than motion: a ByteTrack ID switch between two players, a camera cut, or
# the ball detector latching onto a different white object. Those produce apparent speeds
# far beyond anything physical, and without a ceiling they are recorded as record-breaking
# sprints and shots. Anything above these limits is discarded as a tracking discontinuity.
#
# Usain Bolt's peak is ~12.4 m/s, so a tracked footballer never legitimately exceeds it.
MAX_PLAYER_SPEED = 12.5
# The hardest recorded shots are ~38 m/s; 50 leaves headroom for a genuinely struck ball.
MAX_BALL_SPEED = 50.0

def extract_match_events(match_id, fps=20):
    """
    Analyzes raw spatial TrackingCoordinate data for a match and extracts
    discrete tactical events (possession, passes, interceptions, shots, sprints).
    Saves events into the MatchEvent database table.
    """
    # 1. Clear any existing events to ensure idempotency
    MatchEvent.objects.filter(match_id=match_id).delete()

    try:
        match = Match.objects.get(pk=match_id)
    except Match.DoesNotExist:
        return f"Match {match_id} does not exist."

    # 2. Retrieve coordinates and group by frame
    coordinates = TrackingCoordinate.objects.filter(match_id=match_id).order_by("frame_number")
    if not coordinates.exists():
        return f"No coordinates found for match {match_id}."

    frames = defaultdict(list)
    for coord in coordinates:
        frames[coord.frame_number].append(coord)

    sorted_frames = sorted(frames.keys())

    # State tracking variables
    current_possession_player = None # TrackingCoordinate object or None
    last_possession_player = None    # TrackingCoordinate object or None
    free_ball_frames = 0
    possession_timeout_limit = int(fps * 1.0) # 1 second free ball timeout

    shot_cooldown_frames = 0

    # Sprints tracking: player_id -> {"start_frame", "top_speed", "last_pos", "accumulated_dist", "sprinting_frames"}
    sprint_states = {}

    # Store events to bulk create at the end
    events_to_create = []

    # Goal boundaries (Standard pitch: Goal mouth is at Y between ~30m and ~38m)
    GOAL_Y_MIN = 28.0
    GOAL_Y_MAX = 40.0
    GOAL_LEFT_X = 0.0
    GOAL_RIGHT_X = 105.0

    for i, fn in enumerate(sorted_frames):
        frame_coords = frames[fn]

        # Resolve ball and players
        ball = None
        players = []
        for c in frame_coords:
            if c.player_id == -1:
                ball = c
            elif c.team_classification not in ["referee", "ball"]:
                players.append(c)

        # ─── A. POSSESSION & PASS DETECTION ──────────────────────────────────
        if ball is not None:
            # Find closest player to the ball
            closest_player = None
            min_dist = float("inf")

            for p in players:
                d = distance(p.x_coord, p.y_coord, ball.x_coord, ball.y_coord)
                if d < min_dist:
                    min_dist = d
                    closest_player = p

            # Possession threshold (1.5 meters)
            if min_dist < 1.5:
                free_ball_frames = 0

                # Check for possession changes
                if current_possession_player is None:
                    # New possession established
                    current_possession_player = closest_player

                    events_to_create.append(
                        MatchEvent(
                            match=match,
                            event_type="possession",
                            frame_number=fn,
                            player_initiator=closest_player.player_id,
                            team=closest_player.team_classification,
                            x_coord=closest_player.x_coord,
                            y_coord=closest_player.y_coord,
                            details={"event": "possession_established"}
                        )
                    )
                elif current_possession_player.player_id != closest_player.player_id:
                    # Possession swapped to a different player
                    last_possession_player = current_possession_player
                    current_possession_player = closest_player

                    if last_possession_player.team_classification == closest_player.team_classification:
                        # 1. Success Pass
                        events_to_create.append(
                            MatchEvent(
                                match=match,
                                event_type="pass",
                                frame_number=fn,
                                player_initiator=last_possession_player.player_id,
                                player_receiver=closest_player.player_id,
                                team=closest_player.team_classification,
                                x_coord=closest_player.x_coord,
                                y_coord=closest_player.y_coord,
                                details={"success": True}
                            )
                        )
                    else:
                        # 2. Interception (Failed Pass + Interception Event)
                        events_to_create.append(
                            MatchEvent(
                                match=match,
                                event_type="pass",
                                frame_number=fn,
                                player_initiator=last_possession_player.player_id,
                                player_receiver=closest_player.player_id,
                                team=last_possession_player.team_classification,
                                x_coord=closest_player.x_coord,
                                y_coord=closest_player.y_coord,
                                details={"success": False}
                            )
                        )
                        events_to_create.append(
                            MatchEvent(
                                match=match,
                                event_type="interception",
                                frame_number=fn,
                                player_initiator=last_possession_player.player_id,
                                player_receiver=closest_player.player_id,
                                team=closest_player.team_classification,
                                x_coord=closest_player.x_coord,
                                y_coord=closest_player.y_coord
                            )
                        )
                        events_to_create.append(
                            MatchEvent(
                                match=match,
                                event_type="possession",
                                frame_number=fn,
                                player_initiator=closest_player.player_id,
                                team=closest_player.team_classification,
                                x_coord=closest_player.x_coord,
                                y_coord=closest_player.y_coord,
                                details={"event": "possession_interchanged"}
                            )
                        )
            else:
                # Nearest player is too far from the ball, increment free ball counter
                free_ball_frames += 1
                if free_ball_frames > possession_timeout_limit:
                    if current_possession_player is not None:
                        last_possession_player = current_possession_player
                        current_possession_player = None
        else:
            # Ball missing in this frame, increment free ball counter
            free_ball_frames += 1
            if free_ball_frames > possession_timeout_limit:
                if current_possession_player is not None:
                    last_possession_player = current_possession_player
                    current_possession_player = None

        # ─── B. SHOT DETECTION ───────────────────────────────────────────────
        if shot_cooldown_frames > 0:
            shot_cooldown_frames -= 1

        if shot_cooldown_frames == 0 and ball is not None and i > 0:
            # Check ball velocity (using previous frame ball coords if available)
            prev_frame_num = sorted_frames[i - 1]
            prev_ball = next((c for c in frames[prev_frame_num] if c.player_id == -1), None)

            if prev_ball is not None:
                db = distance(ball.x_coord, ball.y_coord, prev_ball.x_coord, prev_ball.y_coord)
                ball_speed = db * fps # meters per second

                # Shot speed threshold (18.0 m/s = 64.8 km/h), ignoring detector jumps
                if 18.0 < ball_speed <= MAX_BALL_SPEED:
                    dx = ball.x_coord - prev_ball.x_coord
                    dy = ball.y_coord - prev_ball.y_coord

                    if dx != 0:
                        # Goal direction check
                        target_x = GOAL_LEFT_X if dx < 0 else GOAL_RIGHT_X
                        steps = (target_x - ball.x_coord) / dx

                        # Project y coordinate to goal mouth if it reaches in under 2 seconds (40 frames)
                        if 0 < steps < 40:
                            projected_y = ball.y_coord + (steps * dy)
                            if GOAL_Y_MIN <= projected_y <= GOAL_Y_MAX:
                                # Shot detected! Identify the shooter
                                shooter_id = None
                                shooter_team = "unknown"
                                if current_possession_player is not None:
                                    shooter_id = current_possession_player.player_id
                                    shooter_team = current_possession_player.team_classification
                                elif last_possession_player is not None:
                                    shooter_id = last_possession_player.player_id
                                    shooter_team = last_possession_player.team_classification

                                events_to_create.append(
                                    MatchEvent(
                                        match=match,
                                        event_type="shot",
                                        frame_number=fn,
                                        player_initiator=shooter_id,
                                        team=shooter_team,
                                        x_coord=ball.x_coord,
                                        y_coord=ball.y_coord,
                                        details={
                                            "speed_ms": round(ball_speed, 2),
                                            "projected_y": round(projected_y, 2),
                                            "target_goal": "left" if target_x == GOAL_LEFT_X else "right"
                                        }
                                    )
                                )
                                shot_cooldown_frames = int(fps * 1.5) # 1.5 seconds cooldown

        # ─── C. SPRINT DETECTION ─────────────────────────────────────────────
        active_player_ids = set()
        for p in players:
            active_player_ids.add(p.player_id)
            pid = p.player_id

            if pid not in sprint_states:
                # Initialize player tracking
                sprint_states[pid] = {
                    "last_pos": (p.x_coord, p.y_coord),
                    "last_frame": fn,
                    "sprinting_frames": 0,
                    "start_frame": None,
                    "top_speed": 0.0,
                    "accumulated_dist": 0.0
                }
            else:
                state = sprint_states[pid]
                prev_x, prev_y = state["last_pos"]
                prev_fn = state["last_frame"]

                # Compute player speed
                dp = distance(p.x_coord, p.y_coord, prev_x, prev_y)
                dt = (fn - prev_fn) / fps

                if dt > 0:
                    player_speed = dp / dt # meters per second

                    if player_speed > MAX_PLAYER_SPEED:
                        # Not motion - the track jumped. Close out any sprint accumulated from
                        # the plausible frames before it, then resync to the new position so the
                        # bogus displacement is never counted as distance.
                        if state["sprinting_frames"] >= int(fps * 0.5) and state["start_frame"] is not None:
                            duration = (state["last_frame"] - state["start_frame"]) / fps
                            events_to_create.append(
                                MatchEvent(
                                    match=match,
                                    event_type="sprint",
                                    frame_number=state["start_frame"],
                                    player_initiator=pid,
                                    team=p.team_classification,
                                    x_coord=state["last_pos"][0],
                                    y_coord=state["last_pos"][1],
                                    details={
                                        "duration_seconds": round(duration, 2),
                                        "distance_meters": round(state["accumulated_dist"], 2),
                                        "top_speed_ms": round(state["top_speed"], 2),
                                        "ended_by": "tracking_discontinuity"
                                    }
                                )
                            )
                        sprint_states[pid] = {
                            "last_pos": (p.x_coord, p.y_coord),
                            "last_frame": fn,
                            "sprinting_frames": 0,
                            "start_frame": None,
                            "top_speed": 0.0,
                            "accumulated_dist": 0.0
                        }
                        continue

                    # Sprinting speed threshold (7.0 m/s = 25.2 km/h)
                    if player_speed > 7.0:
                        state["sprinting_frames"] += 1
                        state["accumulated_dist"] += dp
                        state["top_speed"] = max(state["top_speed"], player_speed)
                        state["last_pos"] = (p.x_coord, p.y_coord)
                        state["last_frame"] = fn

                        if state["start_frame"] is None:
                            state["start_frame"] = prev_fn
                    else:
                        # Speed dropped below sprinting threshold
                        # Verify if a sprint run has just concluded
                        if state["sprinting_frames"] >= int(fps * 0.5): # at least 0.5s of sprint
                            duration = (fn - state["start_frame"]) / fps
                            events_to_create.append(
                                MatchEvent(
                                    match=match,
                                    event_type="sprint",
                                    frame_number=state["start_frame"],
                                    player_initiator=pid,
                                    team=p.team_classification,
                                    x_coord=p.x_coord,
                                    y_coord=p.y_coord,
                                    details={
                                        "duration_seconds": round(duration, 2),
                                        "distance_meters": round(state["accumulated_dist"], 2),
                                        "top_speed_ms": round(state["top_speed"], 2)
                                    }
                                )
                            )

                        # Reset tracking
                        sprint_states[pid] = {
                            "last_pos": (p.x_coord, p.y_coord),
                            "last_frame": fn,
                            "sprinting_frames": 0,
                            "start_frame": None,
                            "top_speed": 0.0,
                            "accumulated_dist": 0.0
                        }

        # Clear sprint states for players who are no longer on the field / tracking-lost
        for pid in list(sprint_states.keys()):
            if pid not in active_player_ids:
                state = sprint_states[pid]
                if state["sprinting_frames"] >= int(fps * 0.5):
                    # Record sprint that ended due to tracking loss
                    duration = (state["last_frame"] - state["start_frame"]) / fps
                    events_to_create.append(
                        MatchEvent(
                            match=match,
                            event_type="sprint",
                            frame_number=state["start_frame"],
                            player_initiator=pid,
                            team="unknown",
                            x_coord=state["last_pos"][0],
                            y_coord=state["last_pos"][1],
                            details={
                                "duration_seconds": round(duration, 2),
                                "distance_meters": round(state["accumulated_dist"], 2),
                                "top_speed_ms": round(state["top_speed"], 2)
                            }
                        )
                    )
                del sprint_states[pid]

    # Bulk create extracted events
    if events_to_create:
        MatchEvent.objects.bulk_create(events_to_create, batch_size=1000)

    return f"Successfully extracted {len(events_to_create)} tactical events for match {match_id}."
