from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from ...database import supabase


# =========================
# CONFIG ANTI-VOLEUR
# =========================

BLOCK_LEVELS = [
    (3, timedelta(minutes=3)),   # Après 3 échecs → bloqué 3 min
    (6, timedelta(minutes=15)),  # Après 6 échecs → bloqué 15 min
    (9, timedelta(hours=48)),    # Après 9 échecs → bloqué 48h
]

WINDOW_MINUTES = 180  # Fenêtre glissante de 3 heures


def get_recent_attempts(user_id: str, route_id: str, device_id: str):
    """Récupère les tentatives récentes"""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)).isoformat()

    response = supabase.table("route_start_attempts") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("route_id", route_id) \
        .eq("device_id", device_id) \
        .gte("attempted_at", cutoff) \
        .order("attempted_at", desc=True) \
        .execute()

    return response.data or []


def check_block_status(user_id: str, route_id: str, device_id: str):
    """Vérifie si l'utilisateur est bloqué pour cette route sensible"""
    attempts = get_recent_attempts(user_id, route_id, device_id)
    failed_attempts = [a for a in attempts if not a.get("success", False)]

    failed_count = len(failed_attempts)
    if failed_count == 0:
        return {"blocked": False}

    for threshold, block_duration in BLOCK_LEVELS:
        if failed_count >= threshold:
            try:
                last_attempt_str = failed_attempts[0]["attempted_at"]
                last_attempt = datetime.fromisoformat(
                    last_attempt_str.replace("Z", "+00:00")
                )
                block_until = last_attempt + block_duration

                if datetime.now(timezone.utc) < block_until:
                    remaining = int((block_until - datetime.now(timezone.utc)).total_seconds())
                    return {
                        "blocked": True,
                        "remaining_seconds": remaining,
                        "failed_count": failed_count
                    }
            except Exception:
                # En cas de date corrompue, on considère comme non bloqué
                pass
            break  # On applique seulement le premier niveau actif

    return {"blocked": False}


def record_attempt(user_id: str, route_id: str, device_id: str, success: bool):
    """Enregistre une tentative de démarrage"""
    supabase.table("route_start_attempts").insert({
        "user_id": user_id,
        "route_id": route_id,
        "device_id": device_id,
        "success": success
    }).execute()


def get_route(route_id: str):
    """Récupère les infos d'une route"""
    response = supabase.table("routes") \
        .select("id, user_id, route_name, is_sensitive") \
        .eq("id", route_id) \
        .execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Route introuvable")

    return response.data[0]