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
    get_session_alerts_summary,
    get_completed_sessions,
    get_session_alerts_summary,
    get_session_detail,
    delete_session,
    get_history_stats
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
    
# UPLOAD SEGMENT 
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

    # =========================================================
    # RESET si on est revenu clairement sur la route
    # =========================================================
    severity = analysis.get("severity")
    if not analysis.get("is_off_route") and not severity:
        if session.get("last_severity") is not None:
            supabase.table("tracking_sessions").update({
                "last_severity": None,
                "last_alert_distance": None
            }).eq("id", session_id).execute()

    # =========================================================
    # ANTI-SPAM ALERTES
    # - 1er warning dès DANGER (200 m)
    # - Nouveau warning seulement si last_distance >= last_alert_distance + 100 m
    # - Emergency (400 m) : 1 seule fois
    # =========================================================
    last_distance = analysis.get("last_distance") or 0.0
    last_sev = session.get("last_severity")
    last_alert_dist = session.get("last_alert_distance")

    should_alert = False

    if severity == "emergency":
        if last_sev != "emergency":
            should_alert = True
    elif severity == "warning":
        if last_sev is None:
            should_alert = True
        elif last_sev == "warning" and last_alert_dist is not None:
            if last_distance >= last_alert_dist + ALERT_DISTANCE_STEP_M:
                should_alert = True

    if should_alert:
        message = f"DÉVIATION ({round(analysis['max_distance'])}m)"
        alert_id = save_alert(session_id, message, severity)

        for device in get_user_devices(user_id):
            token = device.get("token")
            if token:
                send_push_notification(token, "Safe Route Alert", message)

        try:
            notify_emergency_contacts(user_id, message, alert_id=alert_id)
        except Exception as e:
            logger.error(f"[ALERT] Échec notify_emergency_contacts (alert_id={alert_id}): {e}", exc_info=True)
        # on continue quand même

        # Mémoriser pour le prochain segment
        supabase.table("tracking_sessions").update({
            "last_severity": severity,
            "last_alert_distance": last_distance
        }).eq("id", session_id).execute()

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

def get_history(
    user_id: str,
    route_id: str | None = None,
    has_alerts: bool | None = None,
    from_date: str | None = None,
    to_date: str | None = None
):
    sessions = get_completed_sessions(
        user_id,
        route_id=route_id,
        has_alerts=has_alerts,
        from_date=from_date,
        to_date=to_date
    )
    result = []

    for s in sessions:
        started = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
        ended = None
        if s.get("ended_at"):
            ended = datetime.fromisoformat(s["ended_at"].replace("Z", "+00:00"))

        duration = int((ended - started).total_seconds()) if ended else None
        alerts = get_session_alerts_summary(s["id"])

        result.append({
            "session_id": s["id"],
            "route_id": s["route_id"],
            "route_name": (s.get("routes") or {}).get("route_name"),
            "status": s.get("status"),
            "started_at": s["started_at"],
            "ended_at": s.get("ended_at"),
            "duration_seconds": duration,
            "last_severity": s.get("last_severity"),
            "alert_count": alerts["count"],
            "max_severity": alerts["max_severity"]
        })

    return result


def get_session_history_detail(session_id: str, user_id: str):
    detail = get_session_detail(session_id, user_id)
    if not detail:
        raise HTTPException(404, "Session introuvable dans l'historique.")

    session = detail["session"]
    started = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
    ended = None
    if session.get("ended_at"):
        ended = datetime.fromisoformat(session["ended_at"].replace("Z", "+00:00"))

    duration = int((ended - started).total_seconds()) if ended else None

    # Stats rapides sur les segments
    max_deviation = 0.0
    for seg in detail["segments"]:
        md = seg.get("max_distance_from_route") or 0
        if md > max_deviation:
            max_deviation = md

    return {
        "session_id": session["id"],
        "route_id": session["route_id"],
        "route_name": (session.get("routes") or {}).get("route_name"),
        "is_sensitive": (session.get("routes") or {}).get("is_sensitive", False),
        "status": session.get("status"),
        "started_at": session["started_at"],
        "ended_at": session.get("ended_at"),
        "duration_seconds": duration,
        "last_severity": session.get("last_severity"),
        "max_deviation_meters": round(max_deviation, 1),
        "alerts": detail["alerts"],
        "segments": [
            {
                "id": s["id"],
                "start_time": s.get("start_time"),
                "end_time": s.get("end_time"),
                "avg_distance_from_route": s.get("avg_distance_from_route"),
                "max_distance_from_route": s.get("max_distance_from_route"),
                "points_count": len(s.get("points") or []),
                # On renvoie les points seulement si besoin côté client
                "points": s.get("points") or []
            }
            for s in detail["segments"]
        ]
    }


def delete_history_session(session_id: str, user_id: str):
    deleted = delete_session(session_id, user_id)
    if not deleted:
        raise HTTPException(404, "Session introuvable dans l'historique.")
    return {"success": True, "deleted": deleted}

def get_history_stats_service(
    user_id: str,
    route_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None
):
    return get_history_stats(
        user_id=user_id,
        route_id=route_id,
        from_date=from_date,
        to_date=to_date
    )