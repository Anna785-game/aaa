# tracking/helpers.py

from ...utils import find_closest_point


def serialize_points(points):
    out = []

    for p in points:
        data = p.model_dump() if hasattr(p, "model_dump") else p.dict()

        if data.get("timestamp"):
            data["timestamp"] = data["timestamp"].isoformat()

        out.append(data)

    return out


def calculate_segment_analysis(points, route_points, cfg):
    distances = []
    max_distance = 0.0
    critical = 0

    for p in points:
        d = find_closest_point((p.latitude, p.longitude), route_points)
        distances.append(d)

        max_distance = max(max_distance, d)

        if d > cfg["DANGER"]:
            critical += 1

    avg_distance = sum(distances) / len(distances)
    last_distance = distances[-1]

    is_off_route = (
        avg_distance > cfg["DANGER"]
        or critical >= cfg["MIN_CRITICAL"]
        or last_distance > cfg["DANGER"]
    )

    severity = None

    if critical >= cfg["MIN_CRITICAL"]:
        if max_distance > cfg["EMERGENCY"] and last_distance > cfg["EMERGENCY"]:
            severity = "emergency"
        elif last_distance > cfg["DANGER"]:
            severity = "warning"

    return {
        "avg_distance": avg_distance,
        "max_distance": max_distance,
        "last_distance": last_distance,
        "critical_points_count": critical,
        "is_off_route": is_off_route,
        "severity": severity
    }