from geopy.distance import geodesic
from math import radians, sin, cos, sqrt, atan2

MIN_MOVEMENT_DISTANCE = 5


def calculate_distance(p1, p2):
    return geodesic(p1, p2).meters


def find_closest_point(current_position, route_points):

    closest = float("inf")

    for p in route_points:
        dist = calculate_distance(
            current_position,
            (p["latitude"], p["longitude"])
        )

        if dist < closest:
            closest = dist

    return closest


def calculate_distance_meters(lat1, lon1, lat2, lon2):

    R = 6371000

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def remove_duplicate_points(points):

    cleaned = []
    previous = None

    for point in points:

        current = (
            round(point.latitude, 6),
            round(point.longitude, 6)
        )

        if current != previous:
            cleaned.append(point)
            previous = current

    return cleaned


def is_stationary(points):

    if len(points) < 2:
        return True

    total_distance = 0

    for i in range(1, len(points)):
        prev = points[i - 1]
        curr = points[i]

        total_distance += calculate_distance_meters(
            prev.latitude,
            prev.longitude,
            curr.latitude,
            curr.longitude
        )

    return total_distance < MIN_MOVEMENT_DISTANCE