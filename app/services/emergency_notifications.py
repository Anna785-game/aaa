from ..database import supabase

from .push_notifications import (
    send_push_notification
)

def notify_emergency_contacts(
    requester_id: str,
    message: str
):

    contacts_response = (
        supabase.table(
            "emergency_contacts"
        )
        .select("*")
        .eq(
            "requester_id",
            requester_id
        )
        .eq(
            "status",
            "accepted"
        )
        .execute()
    )

    contacts = (
        contacts_response.data or []
    )

    for contact in contacts:

        target_id = (
            contact["target_id"]
        )

        devices_response = (
            supabase.table(
                "device_tokens"
            )
            .select("*")
            .eq(
                "user_id",
                target_id
            )
            .execute()
        )

        devices = (
            devices_response.data or []
        )

        for device in devices:

            send_push_notification(
                token=device["token"],
                title="Emergency Alert",
                body=message
            )