#emergency_notifications.py

from ..database import supabase

from .push_notifications import (
    send_push_notification,
    send_sms_notification
)

def notify_emergency_contacts(
    requester_id: str,
    message: str
):

    contacts_response = (
        supabase.table("emergency_contacts")
        .select("*")
        .eq("requester_id", requester_id)
        .eq("status", "accepted")
        .execute()
    )

    contacts = contacts_response.data or []

    for contact in contacts:

        target_id = contact.get("target_id")

        if target_id:
            # Contact avec compte → push notification
            devices_response = (
                supabase.table("device_tokens")
                .select("*")
                .eq("user_id", target_id)
                .execute()
            )

            devices = devices_response.data or []

            for device in devices:
                send_push_notification(
                    token=device["token"],
                    title="Emergency Alert",
                    body=message
                )

        else:
            # Contact sans compte → SMS (placeholder)
            send_sms_notification(
                phone_number=contact["target_phone_number"],
                message=message
            )