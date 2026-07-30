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

    # AVANT : la sévérité exigeait au moins MIN_CRITICAL (3) points hors
    # zone DANS LE MÊME SEGMENT. Avec peu de points remontés (GPS throttlé,
    # app en arrière-plan, mauvaise couverture), on pouvait être réellement
    # loin de la route sans jamais atteindre ce seuil -> aucune alerte.
    # MAINTENANT : on se base d'abord sur la position la plus récente
    # (last_distance), qui reflète où l'utilisateur se trouve VRAIMENT
    # au moment de l'upload, peu importe le nombre de points reçus.
    severity = None

    if last_distance > cfg["EMERGENCY"]:
        severity = "emergency"
    elif last_distance > cfg["DANGER"]:
        severity = "warning"
    elif critical >= cfg["MIN_CRITICAL"]:
        # Conservé : plusieurs points du segment étaient loin de la route,
        # même si le tout dernier point est repassé proche (ex: retour rapide)
        severity = "warning"

    return {
        "avg_distance": avg_distance,
        "max_distance": max_distance,
        "last_distance": last_distance,
        "critical_points_count": critical,
        "is_off_route": is_off_route,
        "severity": severity
    }
