#tracking_service.py

import uuid
import logging
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from ...schemas import TrackSegmentRequest, ResumeTrackingRequest
from ...database import supabase
from ...utils import (
    remove_duplicate_points,
    calculate_distance_meters,
    is_stationary
)

from ..tracking_repository import (
    create_tracking_session,
    get_session,
    get_route_points,
    save_segment,
    update_session_checkpoint,
    update_session_checkpoint_manual,
    update_session_status,
    complete_tracking_session,
    save_alert,
    get_user_devices,
    clean_user_route_sessions,
    auto_pause_session,
    resume_auto_paused_session,
    update_stationary_state,
    get_completed_sessions,
    get_session_alerts_summary
)

from ..push_notifications import send_push_notification
from ..emergency_notifications import notify_emergency_contacts

from .config import *
from .helpers import serialize_points, calculate_segment_analysis
from .analysis import compute_trust_inputs
from .validation.motion_detector import validate_motion
from .validation.anomaly_detector import detect_fake_pattern

# === NOUVEAU IMPORT ===
from .security import (
    get_route,
    check_block_status,
    record_attempt
)

logger = logging.getLogger("tracking")


# =========================
# TOLÉRANCE GPS ADAPTATIVE
# =========================

# Tolérance de base, appliquée quand on ne connaît pas la précision GPS
# (ou quand elle est déjà meilleure que ce seuil).
BASE_TOLERANCE_M = 25

# Plafonds : même avec un très mauvais signal GPS, on n'élargit jamais
# au-delà de ça, pour ne pas ouvrir de faille sur les routes sensibles.
MAX_TOLERANCE_SENSITIVE_M = 50
MAX_TOLERANCE_NORMAL_M = 100


def compute_start_tolerance(accuracy: float | None, is_sensitive: bool) -> float:
    """
    Calcule la tolérance autorisée entre la position actuelle et le point
    de départ, en tenant compte de la précision GPS rapportée par le device.
    """
    cap = MAX_TOLERANCE_SENSITIVE_M if is_sensitive else MAX_TOLERANCE_NORMAL_M

    if accuracy is None:
        return BASE_TOLERANCE_M

    return min(cap, BASE_TOLERANCE_M + accuracy)


# =========================
# START SESSION (ANTI-VOLEUR)
# =========================


def start_new_session(
    route_id: str,
    user_id: str,
    device_id: str,
    current_lat: float,
    current_lng: float,
    current_accuracy: float | None = None
):
    """
    Démarrage de session avec protection anti-vol pour routes sensibles
    """
    route = get_route(route_id)

    # Vérification propriétaire
    if route["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé à cette route")

    # === PROTECTION ROUTES SENSIBLES ===
    if route.get("is_sensitive", False):
        block_info = check_block_status(user_id, route_id, device_id)

        if block_info["blocked"]:
            mins = block_info["remaining_seconds"] // 60
            raise HTTPException(
                status_code=429,
                detail=f"Route sensible bloquée pour sécurité. Réessayez dans {mins} minute(s)."
            )

    # === VÉRIFICATION PROXIMITÉ POINT DE DÉPART ===
    route_points = get_route_points(route_id)
    if not route_points:
        raise HTTPException(400, "Cette route ne contient aucun point.")

    start_point = route_points[0]

    dist_to_start = calculate_distance_meters(
        start_point["latitude"], start_point["longitude"],
        current_lat, current_lng
    )

    tolerance = compute_start_tolerance(current_accuracy, route.get("is_sensitive", False))

    if dist_to_start > tolerance:
        if route.get("is_sensitive", False):
            record_attempt(user_id, route_id, device_id, success=False)
        raise HTTPException(
            status_code=400,
             detail=(
                f"Veuillez vous rapprocher du point de départ ({round(dist_to_start)}m). "
                f"Attendu: {start_point['latitude']},{start_point['longitude']} | "
                f"Reçu (toi): {current_lat},{current_lng} | "
                f"Précision GPS: {current_accuracy if current_accuracy is not None else 'inconnue'}m | "
                f"Tolérance: {round(tolerance)}m"
            )
        )
    
    # === SUCCÈS ===
    if route.get("is_sensitive", False):
        record_attempt(user_id, route_id, device_id, success=True)

    # Vérifications de session existante
    existing = supabase.table("tracking_sessions") \
        .select("id") \
        .eq("user_id", user_id) \
        .in_("status", ["active", "paused", "emergency"]) \
        .execute()

    if existing.data:
        raise HTTPException(400, "Une session est déjà active.")

    device_in_use = supabase.table("tracking_sessions") \
        .select("id") \
        .eq("device_id", device_id) \
        .in_("status", ["active", "paused", "emergency"]) \
        .execute()

    if device_in_use.data:
        raise HTTPException(400, "Cet appareil est déjà utilisé dans une session active.")

    # Création de la session
    session_id = str(uuid.uuid4())
    create_tracking_session(session_id, user_id, route_id, device_id)

    return {
        "success": True,
        "session_id": session_id,
        "message": "Session démarrée avec succès"
    }
    
# UPLOAD SEGMENT (inchangé)
# =========================
def upload_tracking_segment(session_id: str, request: TrackSegmentRequest, user_id: str):
    if not request.points:
        raise HTTPException(400, "Segment vide.")

    if len(request.points) > MAX_POINTS_PER_SEGMENT:
        raise HTTPException(400, "Trop de points.")

    request.points = remove_duplicate_points(request.points)

    session = get_session(session_id, user_id)

    request.points, rejected_points = validate_motion(request.points)
    if not request.points:
        raise HTTPException(400, "Tous les points du segment sont invalides")

    fake_pattern = detect_fake_pattern(request.points)

    now = datetime.now(timezone.utc)

    for p in request.points:
        if p.timestamp and p.timestamp > now + timedelta(seconds=30):
            raise HTTPException(400, "Timestamp invalide")

    # === Récupéré une seule fois, réutilisé pour stationary check ET analysis ===
    route_points = get_route_points(session["route_id"])

    # Stationary detection (avec contexte route pour ne pas masquer une déviation)
    stationary = is_stationary(
        request.points,
        route_points=route_points,
        danger_threshold=DANGER_THRESHOLD
    )
    stationary_since = session.get("stationary_since")

    if stationary:
        if not stationary_since:
            update_stationary_state(session_id, True)
            return {
                "success": True,
                "paused": False,
                "state": "stationary_start"
            }

        start_time = datetime.fromisoformat(stationary_since)
        duration = (now - start_time).total_seconds()

        if duration > 300:  # 5 minutes
            auto_pause_session(session_id)
            return {
                "success": True,
                "paused": True,
                "reason": "auto_pause_stationary",
                "duration_seconds": int(duration)
            }

        return {
            "success": True,
            "paused": False,
            "reason": "short_stationary"
        }

    # Movement detected
    if stationary_since:
        resume_auto_paused_session(session_id)

    update_stationary_state(session_id, False)

    trust_score = compute_trust_inputs(
        request.points,
        fake_pattern,
        MAX_TELEPORT_M
    )

    if trust_score < 40:
        raise HTTPException(400, "GPS non fiable")

    analysis = calculate_segment_analysis(
        request.points,
        route_points,
        {
            "DANGER": DANGER_THRESHOLD,
            "EMERGENCY": EMERGENCY_THRESHOLD,
            "MIN_CRITICAL": MIN_CRITICAL_POINTS
        }
    )

    save_segment(
        session_id=session_id,
        request=request,
        serialized_points=serialize_points(request.points),
        analysis=analysis
    )

    update_session_checkpoint(
        session_id=session_id,
        last_point=request.points[-1],
        new_status="emergency" if analysis.get("severity") == "emergency" else "active"
    )

    if analysis.get("severity"):
        message = f"DÉVIATION ({round(analysis['max_distance'])}m)"
        save_alert(session_id, message, analysis["severity"])

        for device in get_user_devices(user_id):
            token = device.get("token")
            if token:
                send_push_notification(token, "Safe Route Alert", message)

        notify_emergency_contacts(user_id, message)

    return {
        "success": True,
        "trust_score": trust_score,
        "severity": analysis.get("severity"),
        "on_route": not analysis.get("is_off_route", True),
        "paused": False
    }

# =========================
# RESUME + COMPLETE (inchangés)
# =========================

def resume_session(session_id: str, request: ResumeTrackingRequest, user_id: str):
    session = get_session(session_id, user_id)

    cp_lat = session.get("last_checkpoint_lat")
    cp_lng = session.get("last_checkpoint_lng")

    if cp_lat is None or cp_lng is None:
        raise HTTPException(400, "Pas de checkpoint disponible.")

    distance = calculate_distance_meters(
        cp_lat, cp_lng, request.latitude, request.longitude
    )

    if distance > HARD_REJECT_DISTANCE:
        raise HTTPException(400, "Distance trop importante - spoof probable")

    if distance <= RESUME_THRESHOLD:
        action = "resume"
    elif distance <= INTERPOLATION_THRESHOLD:
        action = "interpolate"
    else:
        action = "restart_required"

    if action != "restart_required":
        update_session_checkpoint_manual(
            session_id=session_id,
            latitude=request.latitude,
            longitude=request.longitude
        )
        logger.info(f"[RESUME] Session {session_id} reprise ({round(distance, 2)}m)")
    else:
        update_session_status(session_id, "paused")
        auto_pause_session(session_id)
        logger.info(f"[RESUME] Session {session_id} nécessite un redémarrage")

    return {
        "success": action != "restart_required",
        "action": action,
        "distance": round(distance, 2)
    }


def complete_session(session_id: str, user_id: str):
    session = get_session(session_id, user_id)
    complete_tracking_session(session_id)
    clean_user_route_sessions(user_id, session["route_id"])

    return {"success": True}

# =========================
# HISTORIC
# =========================

def get_history(user_id: str, route_id: str | None = None):
    sessions = get_completed_sessions(user_id, route_id)
    result = []

    for s in sessions:
        started = datetime.fromisoformat(s["started_at"])
        ended = datetime.fromisoformat(s["ended_at"]) if s.get("ended_at") else None
        duration = int((ended - started).total_seconds()) if ended else None
        alerts = get_session_alerts_summary(s["id"])

        result.append({
            "session_id": s["id"],
            "route_id": s["route_id"],
            "route_name": (s.get("routes") or {}).get("route_name"),
            "started_at": s["started_at"],
            "ended_at": s.get("ended_at"),
            "duration_seconds": duration,
            "last_severity": s.get("last_severity"),
            "alert_count": alerts["count"],
            "max_severity": alerts["max_severity"]
        })

    return result