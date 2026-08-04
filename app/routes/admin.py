#admin.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from ..database import supabase
from ..dependencies import get_current_user
from ..admin_config import ADMIN_USER_ID
from ..schemas import DeviceTokenRegister

router = APIRouter(prefix="/admin", tags=["Admin"])


def require_admin(current_user=Depends(get_current_user)):
    if not ADMIN_USER_ID or current_user["user_id"] != ADMIN_USER_ID:
        raise HTTPException(status_code=403, detail="Accès refusé.")
    return current_user


# =========================
# ENREGISTRER TON APP FLUTTER ADMIN
# =========================

@router.post("/register-device")
def register_admin_device(
    payload: DeviceTokenRegister,
    _=Depends(require_admin)
):
    existing = (
        supabase.table("admin_devices")
        .select("*")
        .eq("token", payload.token)
        .execute()
    )

    if existing.data:
        supabase.table("admin_devices").update({
            "platform": payload.platform,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("token", payload.token).execute()
    else:
        supabase.table("admin_devices").insert({
            "token": payload.token,
            "platform": payload.platform
        }).execute()

    return {"success": True}


# =========================
# FILE D'ATTENTE SMS À RELAYER
# =========================

@router.get("/relay-queue")
def get_relay_queue(_=Depends(require_admin)):
    res = (
        supabase.table("sms_relay_queue")
        .select("*")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .execute()
    )
    return {"queue": res.data or []}


@router.post("/relay-queue/{item_id}/resolve")
def resolve_relay_item(item_id: str, _=Depends(require_admin)):
    res = (
        supabase.table("sms_relay_queue")
        .update({
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat()
        })
        .eq("id", item_id)
        .eq("status", "pending")
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="Introuvable ou déjà traité.")

    return {"success": True}