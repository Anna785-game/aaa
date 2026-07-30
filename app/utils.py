#utils.py

from geopy.distance import geodesic
from math import radians, sin, cos, sqrt, atan2

MIN_MOVEMENT_DISTANCE = 5


def calculate_distance(p1, p2):
    return geodesic(p1, p2).meters


def calculate_distance_meters(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def _point_to_segment_distance_m(px, py, ax, ay, bx, by):
    """
    Distance approximative (mètres) entre le point P et le segment [A, B].
    On travaille dans un plan localement plat (approximation valable
    pour des segments courts, quelques centaines de mètres max) en
    convertissant les degrés en mètres via des facteurs d'échelle locaux.
    """
    # Facteurs d'échelle locaux (mètres par degré) autour du point A
    lat_ref = ax
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * cos(radians(lat_ref))

    ax_m, ay_m = 0.0, 0.0
    bx_m = (by - ay) * m_per_deg_lon
    by_m = (bx - ax) * m_per_deg_lat
    px_m = (py - ay) * m_per_deg_lon
    py_m = (px - ax) * m_per_deg_lat

    dx, dy = bx_m - ax_m, by_m - ay_m
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0:
        # A == B, on retombe sur une distance point-point classique
        return calculate_distance_meters(ax, ay, px, py)

    # Projection de P sur la droite (A,B), clampée entre 0 et 1 pour
    # rester sur le segment (pas la droite infinie)
    t = ((px_m - ax_m) * dx + (py_m - ay_m) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))

    proj_x = ax_m + t * dx
    proj_y = ay_m + t * dy

    return sqrt((px_m - proj_x) ** 2 + (py_m - proj_y) ** 2)


def find_closest_point(current_position, route_points):
    """
    Distance minimale entre la position actuelle et le TRAJET
    (la ligne brisée reliant les points), pas seulement les points
    eux-mêmes. Corrige le cas où deux points de route sont éloignés :
    le milieu du segment n'est plus faussement "loin" du trajet.
    """
    if not route_points:
        return float("inf")

    if len(route_points) == 1:
        return calculate_distance(
            current_position,
            (route_points[0]["latitude"], route_points[0]["longitude"])
        )

    px, py = current_position
    closest = float("inf")

    for i in range(1, len(route_points)):
        a = route_points[i - 1]
        b = route_points[i]
        d = _point_to_segment_distance_m(
            px, py,
            a["latitude"], a["longitude"],
            b["latitude"], b["longitude"]
        )
        if d < closest:
            closest = d

    return closest


def remove_duplicate_points(points):
    cleaned = []
    previous = None
    for point in points:
        current = (round(point.latitude, 6), round(point.longitude, 6))
        if current != previous:
            cleaned.append(point)
            previous = current
    return cleaned


def is_stationary(points, route_points=None, danger_threshold=None):
    """
    Détermine si l'utilisateur est immobile.
    IMPORTANT : si on est immobile MAIS loin de la trajectoire, on ne doit
    PAS le traiter comme "stationary" — sinon le code appelant saute
    complètement l'analyse de déviation et aucune alerte ne part.
    On ne renvoie True que si peu de mouvement ET (pas d'info de route
    OU suffisamment proche de la route).
    """
    if len(points) < 2:
        moved_enough = False
    else:
        total_distance = 0
        for i in range(1, len(points)):
            prev = points[i - 1]
            curr = points[i]
            total_distance += calculate_distance_meters(
                prev.latitude, prev.longitude, curr.latitude, curr.longitude
            )
        moved_enough = total_distance >= MIN_MOVEMENT_DISTANCE

    if moved_enough:
        return False

    # Peu ou pas de mouvement : on vérifie si on est loin de la route
    # avant de confirmer le statut "stationary"
    if route_points and danger_threshold is not None:
        last = points[-1]
        dist_to_route = find_closest_point(
            (last.latitude, last.longitude), route_points
        )
        if dist_to_route > danger_threshold:
            return False  # Immobile mais hors trajectoire -> pas "stationary"

    return True