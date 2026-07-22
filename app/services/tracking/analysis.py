# tracking/analysis.py
from ...utils import calculate_distance_meters
from .validation.trust_score import compute_trust_score


def compute_trust_inputs(points, fake_pattern, max_teleport_m):
    if len(points) < 2:
        return 100

    total_distance = 0

    for i in range(1, len(points)):
        total_distance += calculate_distance_meters(
            points[i-1].latitude,
            points[i-1].longitude,
            points[i].latitude,
            points[i].longitude
        )

    time_span = None
    if points[0].timestamp and points[-1].timestamp:
        time_span = (points[-1].timestamp - points[0].timestamp).total_seconds()

    speed_violation = (
        time_span is not None
        and time_span > 0
        and (total_distance / time_span) > 50
    )

    teleport = False

    for i in range(1, len(points)):
        d = calculate_distance_meters(
            points[i-1].latitude,
            points[i-1].longitude,
            points[i].latitude,
            points[i].longitude
        )

        if d > max_teleport_m:
            teleport = True
            break

    return compute_trust_score(
        speed_violation=speed_violation,
        teleport=teleport,
        fake_pattern=fake_pattern
    )