#tracking/validation/motion_detector.py

from fastapi import HTTPException
from ....utils import calculate_distance_meters
from ..config import MAX_SPEED_M_S, MAX_ACCEL_M_S2, MAX_TELEPORT_M


def validate_motion(points):
    if len(points) < 2:
        return

    prev_speed = None

    for i in range(1, len(points)):
        p1, p2 = points[i - 1], points[i]

        if not p1.timestamp or not p2.timestamp:
            continue

        dt = (p2.timestamp - p1.timestamp).total_seconds()

        if dt <= 0:
            raise HTTPException(400, "Timestamp invalide")

        dist = calculate_distance_meters(
            p1.latitude, p1.longitude,
            p2.latitude, p2.longitude
        )

        if dist > MAX_TELEPORT_M:
            raise HTTPException(400, "Téléportation GPS détectée")

        speed = dist / dt

        if speed > MAX_SPEED_M_S:
            raise HTTPException(400, "Vitesse impossible détectée")

        if prev_speed is not None:
            accel = abs(speed - prev_speed) / dt

            if accel > MAX_ACCEL_M_S2:
                raise HTTPException(400, "Accélération GPS impossible")

        prev_speed = speed