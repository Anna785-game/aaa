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

    supabase.table("alerts").insert({
        "session_id": session_id,
        "message": message,
        "severity": severity
    }).execute()


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
    
