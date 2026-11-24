"""Simple, explicit energy budget for the simulated robot (percentage units)."""

BASE_PER_SECOND = 0.008
DRIVE_PER_METRE = 0.55
TURN_PER_RADIAN = 0.025
CAMERA_PER_SECOND = 0.035
INFERENCE_PER_SECOND = 0.08
RETURN_MARGIN = 8.0


def return_reserve(route_distance):
    """Energy needed to retrace the route, plus a safety margin."""
    return RETURN_MARGIN + max(0.0, route_distance) * DRIVE_PER_METRE * 1.25
