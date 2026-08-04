#emergency_notifications.py
from ..database import supabase
from .push_notifications import send_push_notification


def _get_admin_tokens():
    res = supabase.table("admin_devices").select("token").execute()
    return [d["token"] for d in (res.data or [])]


def _queue_sms_relay(alert_id, contact_name, contact_phone, message):
    res = supabase.table("sms_relay_queue").insert({
        "alert_id": alert_id,
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "message": message,
        "status": "pending"
    }).execute()
    return res.data[0] if res.data else None


def _notify_admin_relay(relay_item):
    payload = {
        "type": "sms_relay",
        "relay_id": relay_item["id"],
        "alert_id": relay_item["alert_id"],
        "contact_name": relay_item["contact_name"],
        "contact_phone": relay_item["contact_phone"],
        "message": relay_item["message"]
    }

    for token in _get_admin_tokens():
        send_push_notification(
            token=token,
            title="Relais SMS requis",
            body=f"{relay_item['contact_name']} ({relay_item['contact_phone']})",
            data=payload
        )


def notify_emergency_contacts(requester_id: str, message: str, alert_id: str | None = None):
    """
    Tout passe par la file d'attente admin.
    Plus de push direct aux contacts, même s'ils ont un compte.
    """

    if not alert_id:
        # Sans alert_id on ne peut pas créer d'entrée dans la queue
        return

    contacts_response = (
        supabase.table("emergency_contacts")
        .select("*")
        .eq("requester_id", requester_id)
        .eq("status", "active")
        .execute()
    )

    contacts = contacts_response.data or []

    for contact in contacts:
        relay_item = _queue_sms_relay(
            alert_id=alert_id,
            contact_name=contact["target_full_name"],
            contact_phone=contact["target_phone_number"],
            message=message
        )
        if relay_item:
            _notify_admin_relay(relay_item)