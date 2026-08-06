#tracking_repository.py
from datetime import datetime, timezone
from fastapi import HTTPException
from ..database import supabase


# =========================
# SESSION
# =========================

def create_tracking_session(session_id: str, user_id: str, route_id: str, device_id: str):

    now = datetime.now(timezone.utc).isoformat()

    supabase.table("tracking_sessions").insert({
        "id": session_id,
        "user_id": user_id,
        "route_id": route_id,
        "device_id": device_id,
        "status": "active",
        "auto_paused": False,
        "last_checkpoint_time": now,
        "last_segment_upload": now,
        "last_checkpoint_lat": None,
        "last_checkpoint_lng": None,
        "stationary_since": None,
        "last_severity": None,
        "started_at": now
    }).execute()


def get_session(session_id: str, user_id: str):

    res = supabase.table("tracking_sessions") \
        .select("*") \
        .eq("id", session_id) \
        .eq("user_id", user_id) \
        .execute()

    if not res.data:
        raise HTTPException(404, "Session introuvable")

    return res.data[0]


# =========================
# CHECKPOINT (AMÉLIORÉ)
# =========================

def update_session_checkpoint(session_id: str, last_point, new_status: str):
    """Met à jour le checkpoint principal (utilisé lors des uploads normaux)"""
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("tracking_sessions").update({
        "last_checkpoint_lat": last_point.latitude,
        "last_checkpoint_lng": last_point.longitude,
        "last_checkpoint_time": now,
        "last_segment_upload": now,
        "status": new_status,
        "stationary_since": None,           # On reset l'immobilité quand on reçoit des points
        "auto_paused": False
    }).eq("id", session_id).execute()


def update_session_checkpoint_manual(session_id: str, latitude: float, longitude: float):
    """Version pour le resume manuel (plus légère)"""
    now = datetime.now(timezone.utc).isoformat()

    supabase.table("tracking_sessions").update({
        "last_checkpoint_lat": latitude,
        "last_checkpoint_lng": longitude,
        "last_checkpoint_time": now,
        "last_segment_upload": now,
        "status": "active",
        "stationary_since": None,
        "auto_paused": False,
        "last_severity": None
    }).eq("id", session_id).execute()


def update_session_status(session_id: str, status: str):

    supabase.table("tracking_sessions").update({
        "status": status
    }).eq("id", session_id).execute()


def complete_tracking_session(session_id: str):

    now = datetime.now(timezone.utc).isoformat()

    supabase.table("tracking_sessions").update({
        "status": "completed",
        "ended_at": now
    }).eq("id", session_id).execute()


# =========================
# AUTO STATE
# =========================

def auto_pause_session(session_id: str):

    supabase.table("tracking_sessions").update({
        "status": "paused",
        "auto_paused": True
    }).eq("id", session_id).execute()


def resume_auto_paused_session(session_id: str):

    supabase.table("tracking_sessions").update({
        "status": "active",
        "auto_paused": False,
        "stationary_since": None
    }).eq("id", session_id).execute()


def update_stationary_state(session_id: str, started: bool):

    value = datetime.now(timezone.utc).isoformat() if started else None

    supabase.table("tracking_sessions").update({
        "stationary_since": value
    }).eq("id", session_id).execute()


# =========================
# ROUTES
# =========================

def get_route_points(route_id: str):

    res = supabase.table("route_points") \
        .select("*") \
        .eq("route_id", route_id) \
        .order("order_index") \
        .execute()

    return res.data or []


# =========================
# SEGMENTS
# =========================

def save_segment(session_id: str, request, serialized_points, analysis):

    start_time = request.points[0].timestamp.isoformat() if request.points[0].timestamp else None
    end_time = request.points[-1].timestamp.isoformat() if request.points[-1].timestamp else None

    supabase.table("tracking_segments").insert({
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "points": serialized_points,
        "avg_distance_from_route": analysis["avg_distance"],
        "max_distance_from_route": analysis["max_distance"],
        "status": "finalized"
    }).execute()


# =========================
# ALERTS
# =========================

def save_alert(session_id: str, message: str, severity: str):

    res = supabase.table("alerts").insert({
        "session_id": session_id,
        "message": message,
        "severity": severity
    }).execute()

    return res.data[0]["id"] if res.data else None

# =========================
# DEVICES
# =========================

def get_user_devices(user_id: str):

    res = supabase.table("device_tokens") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    return res.data or []


# =========================
# CLEANUP
# =========================

def clean_user_route_sessions(user_id: str, route_id: str):

    supabase.rpc(
        "clean_user_route_sessions",
        {
            "target_user_id": user_id,
            "target_route_id": route_id
        }
    ).execute()
    
# =========================
# HISTORY
# =========================

# =========================
# HISTORY
# =========================

def get_completed_sessions(
    user_id: str,
    route_id: str = None,
    limit: int = 21,
    has_alerts: bool = None,
    from_date: str = None,
    to_date: str = None
):
    """
    Récupère les sessions terminées + emergency.
    """
    query = supabase.table("tracking_sessions") \
        .select("id, route_id, started_at, ended_at, last_severity, status, routes(route_name)") \
        .eq("user_id", user_id) \
        .in_("status", ["completed", "emergency"]) \
        .order("started_at", desc=True) \
        .limit(limit)

    if route_id:
        query = query.eq("route_id", route_id)

    if from_date:
        query = query.gte("started_at", from_date)

    if to_date:
        query = query.lte("started_at", to_date)

    res = query.execute()
    sessions = res.data or []

    # Filtre "avec alertes" côté Python (plus simple que sous-requête)
    if has_alerts is True:
        filtered = []
        for s in sessions:
            alerts = get_session_alerts_summary(s["id"])
            if alerts["count"] > 0:
                filtered.append(s)
        return filtered

    return sessions


def get_session_alerts_summary(session_id: str):
    res = supabase.table("alerts") \
        .select("severity") \
        .eq("session_id", session_id) \
        .execute()

    data = res.data or []
    max_sev = None
    if any(a["severity"] == "emergency" for a in data):
        max_sev = "emergency"
    elif any(a["severity"] == "warning" for a in data):
        max_sev = "warning"

    return {"count": len(data), "max_severity": max_sev}


def get_session_detail(session_id: str, user_id: str):
    """Détail complet d'une session + alertes + segments."""
    session_res = supabase.table("tracking_sessions") \
        .select("*, routes(route_name, is_sensitive)") \
        .eq("id", session_id) \
        .eq("user_id", user_id) \
        .in_("status", ["completed", "emergency"]) \
        .execute()

    if not session_res.data:
        return None

    session = session_res.data[0]

    # Alertes
    alerts_res = supabase.table("alerts") \
        .select("id, message, severity, last_known_lat, last_known_lng, created_at") \
        .eq("session_id", session_id) \
        .order("created_at") \
        .execute()

    # Segments (points GPS stockés)
    segments_res = supabase.table("tracking_segments") \
        .select("id, start_time, end_time, avg_distance_from_route, max_distance_from_route, points") \
        .eq("session_id", session_id) \
        .order("start_time") \
        .execute()

    return {
        "session": session,
        "alerts": alerts_res.data or [],
        "segments": segments_res.data or []
    }


def delete_session(session_id: str, user_id: str):
    """
    Supprime une session et tout ce qui y est lié
    (segments + alerts) grâce aux CASCADE.
    """
    res = supabase.table("tracking_sessions") \
        .delete() \
        .eq("id", session_id) \
        .eq("user_id", user_id) \
        .in_("status", ["completed", "emergency"]) \
        .execute()

    return res.data

def get_history_stats(
    user_id: str,
    route_id: str = None,
    from_date: str = None,
    to_date: str = None
):
    """
    Agrégats simples sur les sessions completed + emergency.
    """
    query = supabase.table("tracking_sessions") \
        .select("id, started_at, ended_at, last_severity, status, route_id") \
        .eq("user_id", user_id) \
        .in_("status", ["completed", "emergency"])

    if route_id:
        query = query.eq("route_id", route_id)
    if from_date:
        query = query.gte("started_at", from_date)
    if to_date:
        query = query.lte("started_at", to_date)

    sessions = query.execute().data or []

    total_sessions = len(sessions)
    emergency_sessions = 0
    completed_sessions = 0
    sessions_with_alerts = 0
    total_duration = 0
    durations = []

    alert_warning = 0
    alert_emergency = 0

    for s in sessions:
        status = s.get("status")
        if status == "emergency":
            emergency_sessions += 1
        else:
            completed_sessions += 1

        # Durée
        if s.get("started_at") and s.get("ended_at"):
            try:
                started = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
                ended = datetime.fromisoformat(s["ended_at"].replace("Z", "+00:00"))
                dur = int((ended - started).total_seconds())
                if dur > 0:
                    total_duration += dur
                    durations.append(dur)
            except Exception:
                pass

        # Alertes de cette session
        alerts_res = supabase.table("alerts") \
            .select("severity") \
            .eq("session_id", s["id"]) \
            .execute()

        alerts = alerts_res.data or []
        if alerts:
            sessions_with_alerts += 1
            for a in alerts:
                if a["severity"] == "emergency":
                    alert_emergency += 1
                else:
                    alert_warning += 1

    avg_duration = int(total_duration / len(durations)) if durations else 0

    return {
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "emergency_sessions": emergency_sessions,
        "sessions_with_alerts": sessions_with_alerts,
        "clean_sessions": total_sessions - sessions_with_alerts,
        "total_alerts": alert_warning + alert_emergency,
        "warning_alerts": alert_warning,
        "emergency_alerts": alert_emergency,
        "total_duration_seconds": total_duration,
        "avg_duration_seconds": avg_duration,
    }