#background_watchdog.py
import time
import logging
from datetime import datetime, timezone, timedelta

from ..database import supabase
from ..services.push_notifications import send_push_notification
from ..services.emergency_notifications import notify_emergency_contacts, _get_admin_tokens
from ..services.tracking_repository import get_user_devices

# =========================
# CONFIG
# =========================

TIMEOUT_MINUTES = 20                    # 20 minutes sans activité = perte de signal
CHECK_INTERVAL_SECONDS = 60
MIN_ALERT_INTERVAL_MINUTES = 30         # Anti-spam : max 1 alerte toutes les 30 min
RELAY_RETRY_MINUTES = 5                 # Relance les SMS en attente après 5 min

logger = logging.getLogger("watchdog")
logging.basicConfig(level=logging.INFO)


# =========================
# WATCHDOG – PERTE DE SIGNAL
# =========================

def check_lost_sessions():
    try:
        cutoff_time = (
            datetime.now(timezone.utc) - timedelta(minutes=TIMEOUT_MINUTES)
        ).isoformat()

        sessions = (
            supabase.table("tracking_sessions")
            .select("id, user_id, last_checkpoint_lat, last_checkpoint_lng")
            .eq("status", "active")
            .lt("last_checkpoint_time", cutoff_time)
            .execute()
        ).data or []

        for session in sessions:
            session_id = session["id"]
            user_id = session["user_id"]

            # --- Anti-doublons ---
            recent_alert = (
                supabase.table("alerts")
                .select("created_at")
                .eq("session_id", session_id)
                .eq("severity", "emergency")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            ).data

            if recent_alert:
                last_alert_time = datetime.fromisoformat(
                    recent_alert[0]["created_at"].replace("Z", "+00:00")
                )
                if (datetime.now(timezone.utc) - last_alert_time).total_seconds() < MIN_ALERT_INTERVAL_MINUTES * 60:
                    continue

            # --- Mise à jour atomique ---
            updated = (
                supabase.table("tracking_sessions")
                .update({
                    "status": "emergency",
                    "last_severity": "emergency"
                })
                .eq("id", session_id)
                .eq("status", "active")
                .execute()
            )

            if not updated.data:
                continue

            # --- Création alerte ---
            message = f"ALERTE : Perte de signal prolongée ({TIMEOUT_MINUTES} minutes sans mise à jour GPS)"

            alert_res = supabase.table("alerts").insert({
                "session_id": session_id,
                "message": message,
                "severity": "emergency",
                "last_known_lat": session.get("last_checkpoint_lat"),
                "last_known_lng": session.get("last_checkpoint_lng")
            }).execute()

            alert_id = alert_res.data[0]["id"] if alert_res.data else None

            # --- Notifications utilisateur ---
            devices = get_user_devices(user_id)
            for device in devices:
                token = device.get("token")
                if token:
                    send_push_notification(token, "Emergency Alert", message)

            # --- File d'attente admin (SMS) ---
            if alert_id:
                notify_emergency_contacts(user_id, message, alert_id=alert_id)

            logger.info(f"[WATCHDOG] Emergency → Session {session_id} (user {user_id})")

    except Exception as e:
        logger.error(f"[WATCHDOG ERROR] {e}", exc_info=True)


# =========================
# RELANCE DES RELAIS SMS EN ATTENTE
# =========================

def retry_pending_relays():
    try:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=RELAY_RETRY_MINUTES)
        ).isoformat()

        # On ne relance QUE les items dont la dernière notif date de plus
        # de RELAY_RETRY_MINUTES (pas juste la création) -> évite le spam
        # à chaque tick du watchdog (60s) une fois le cutoff dépassé.
        pending = (
            supabase.table("sms_relay_queue")
            .select("*")
            .eq("status", "pending")
            .lt("last_notified_at", cutoff)
            .execute()
        ).data or []

        for item in pending:
            for token in _get_admin_tokens():
                send_push_notification(
                    token=token,
                    title="⚠️ Relais SMS toujours en attente",
                    body=f"{item['contact_name']} ({item['contact_phone']})",
                    data={
                        "type": "sms_relay",
                        "relay_id": item["id"],
                        "alert_id": item["alert_id"],
                        "contact_name": item["contact_name"],
                        "contact_phone": item["contact_phone"],
                        "message": item["message"]
                    }
                )

            # On met à jour last_notified_at pour ne pas re-notifier
            # avant le prochain intervalle
            supabase.table("sms_relay_queue").update({
                "last_notified_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", item["id"]).execute()

            logger.info(f"[WATCHDOG] Relance relais SMS → {item['id']}")

    except Exception as e:
        logger.error(f"[WATCHDOG ERROR - relay] {e}", exc_info=True)

# =========================
# LANCEMENT
# =========================

if __name__ == "__main__":
    logger.info(f"[WATCHDOG] Démarré - Timeout: {TIMEOUT_MINUTES} minutes | Retry relay: {RELAY_RETRY_MINUTES} minutes")
    while True:
        check_lost_sessions()
        retry_pending_relays()
        time.sleep(CHECK_INTERVAL_SECONDS)