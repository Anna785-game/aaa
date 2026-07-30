#tracking/validation/motion_detector.py
from ....utils import calculate_distance_meters
from ..config import MAX_SPEED_M_S, MAX_ACCEL_M_S2, MAX_TELEPORT_M

# En dessous de ce dt, le bruit GPS domine largement le signal de vitesse
# réel (un smartphone peut donner deux fixes à 200-400ms d'intervalle avec
# quelques mètres d'écart parasite -> "vitesse" de 20-50 km/h fantôme).
MIN_DT_FOR_SPEED_CHECK = 1.0


def filter_motion_anomalies(points):
    """
    Retourne (points_valides, points_rejetes).
    Au lieu de faire échouer tout le segment sur UN point aberrant
    (téléportation / vitesse / accélération), on retire ce point précis
    et on garde le reste. On ne lève une erreur que si le segment entier
    est incohérent (trop de rejets).
    """
    if len(points) < 2:
        return points, []

    valid = [points[0]]
    rejected = []
    prev_speed = None

    for i in range(1, len(points)):
        p_prev = valid[-1]
        p_curr = points[i]

        if not p_prev.timestamp or not p_curr.timestamp:
            valid.append(p_curr)
            continue

        dt = (p_curr.timestamp - p_prev.timestamp).total_seconds()

        if dt <= 0:
            # Timestamp incohérent -> on ignore ce point plutôt que de
            # planter tout le segment
            rejected.append(p_curr)
            continue

        dist = calculate_distance_meters(
            p_prev.latitude, p_prev.longitude,
            p_curr.latitude, p_curr.longitude
        )

        if dist > MAX_TELEPORT_M:
            rejected.append(p_curr)
            continue

        speed = dist / dt

        # On ne juge la vitesse/accélération fiable qu'au-delà d'un dt
        # minimal, pour éviter les faux positifs de bruit GPS
        if dt >= MIN_DT_FOR_SPEED_CHECK:
            if speed > MAX_SPEED_M_S:
                rejected.append(p_curr)
                continue

            if prev_speed is not None:
                accel = abs(speed - prev_speed) / dt
                if accel > MAX_ACCEL_M_S2:
                    rejected.append(p_curr)
                    continue

            prev_speed = speed

        valid.append(p_curr)

    return valid, rejected


def validate_motion(points):
    """
    Garde la compatibilité avec l'appel existant : lève une exception
    UNIQUEMENT si le segment est majoritairement incohérent (spoof
    probable), sinon laisse passer avec filtrage silencieux des points
    aberrants isolés.
    """
    from fastapi import HTTPException

    valid, rejected = filter_motion_anomalies(points)

    # Si plus de la moitié des points sont rejetés, quelque chose de
    # sérieux se passe (vrai spoof GPS) -> on bloque pour de vrai
    if len(points) >= 4 and len(rejected) > len(points) / 2:
        raise HTTPException(400, "Mouvement GPS incohérent détecté")

    return valid, rejected