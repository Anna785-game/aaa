#tracking/validation/anomaly_detector.py
import statistics
from ....utils import calculate_distance_meters
from ..config import MIN_VARIANCE_THRESHOLD


def detect_fake_pattern(points):
    if len(points) < 5:
        return False

    distances = []

    for i in range(1, len(points)):
        distances.append(
            calculate_distance_meters(
                points[i-1].latitude,
                points[i-1].longitude,
                points[i].latitude,
                points[i].longitude
            )
        )

    variance = statistics.pvariance(distances)

    return variance < MIN_VARIANCE_THRESHOLD and sum(distances) > 100