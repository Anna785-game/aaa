from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from ..main import limiter
from ..database import supabase
from ..schemas import DeviceTokenRegister
from ..dependencies import get_current_user

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)

# =========================
# REGISTER DEVICE TOKEN
# =========================

@router.post("/register-device")
@limiter.limit("10/minute")
def register_device(
    request_http: Request,
    request: DeviceTokenRegister,
    current_user=Depends(get_current_user)
):

    existing = (
        supabase.table("device_tokens")
        .select("*")
        .eq("token", request.token)
        .execute()
    )

    # -------------------------
    # UPDATE EXISTING
    # -------------------------

    if existing.data:

        supabase.table("device_tokens").update({

            "user_id":
                current_user["user_id"],

            "platform":
                request.platform

        }).eq(
            "token",
            request.token
        ).execute()

    # -------------------------
    # INSERT NEW
    # -------------------------

    else:

        supabase.table("device_tokens").insert({

            "user_id":
                current_user["user_id"],

            "token":
                request.token,

            "platform":
                request.platform

        }).execute()

    return {
        "success": True,
        "message": "Device enregistré."
    }

# =========================
# LIST DEVICES
# =========================

@router.get("/my-devices")
def my_devices(
    current_user=Depends(get_current_user)
):

    response = (
        supabase.table("device_tokens")
        .select("*")
        .eq(
            "user_id",
            current_user["user_id"]
        )
        .execute()
    )

    return {
        "devices": response.data
    }

# =========================
# DELETE DEVICE
# =========================

@router.delete("/delete-device/{token}")
def delete_device(
    token: str,
    current_user=Depends(get_current_user)
):

    response = (
        supabase.table("device_tokens")
        .delete()
        .eq("token", token)
        .eq(
            "user_id",
            current_user["user_id"]
        )
        .execute()
    )

    return {
        "success": True,
        "deleted": response.data
    }