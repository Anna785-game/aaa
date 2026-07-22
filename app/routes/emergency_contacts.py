import random
import string

from datetime import (
    datetime,
    timedelta,
    timezone
)

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request
)
from ..main import limiter

from ..database import supabase
from ..dependencies import get_current_user

from ..schemas import (
    EmergencyContactCreate,
    EmergencyContactConfirm
)

router = APIRouter(
    prefix="/emergency-contacts",
    tags=["Emergency Contacts"]
)

# =========================
# HELPERS
# =========================

def get_user_profile(user_id: str):

    response = (
        supabase.table("profiles")
        .select("*")
        .eq("id", user_id)
        .execute()
    )

    if not response.data:

        raise HTTPException(
            status_code=400,
            detail=(
                "Profil requis avant "
                "d'utiliser cette fonctionnalité."
            )
        )

    return response.data[0]


def generate_code():

    return ''.join(
        random.choices(
            string.digits,
            k=6
        )
    )

# =========================
# ADD CONTACT
# =========================

@router.post("/add")
@limiter.limit("5/minute")
def add_emergency_contact(
    request_http: Request,
    request: EmergencyContactCreate,
    current_user=Depends(get_current_user)
):

    get_user_profile(current_user["user_id"])

    # FIND TARGET PROFILE
    target_response = (
        supabase.table("profiles")
        .select("*")
        .eq("full_name", request.full_name)
        .eq("phone_number", request.phone_number)
        .execute()
    )

    if not target_response.data:
        raise HTTPException(
            status_code=404,
            detail="Profil introuvable."
        )

    target = target_response.data[0]

    # BLOCK SELF ADD
    if target["id"] == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="Impossible de s'ajouter soi-même."
        )

    # EXISTING REQUEST
    existing = (
        supabase.table("emergency_contacts")
        .select("*")
        .eq("requester_id", current_user["user_id"])
        .eq("target_id", target["id"])
        .execute()
    )

    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="Demande déjà existante."
        )

    code = generate_code()

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    ).isoformat()

    supabase.table("emergency_contacts").insert({

        "requester_id": current_user["user_id"],
        "target_id": target["id"],
        "relationship": request.relationship,
        "verification_code": code,
        "verification_expires_at": expires_at,
        "status": "pending",
        "failed_attempts": 0

    }).execute()

    return {
        "success": True,
        "message": "Demande envoyée.",
        "verification_code": code
    }

# =========================
# CONFIRM CONTACT
# =========================

@router.post("/confirm/{request_id}")
@limiter.limit("10/minute")
def confirm_contact(
    request_http: Request,
    request_id: str,
    request: EmergencyContactConfirm,
    current_user=Depends(get_current_user)
):

    get_user_profile(current_user["user_id"])

    response = (
        supabase.table("emergency_contacts")
        .select("*")
        .eq("id", request_id)
        .eq("target_id", current_user["user_id"])
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail="Demande introuvable."
        )

    contact = response.data[0]

    if contact["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail="Demande invalide."
        )

    # BLOCK BRUTE FORCE
    if contact.get("failed_attempts", 0) >= 5:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives."
        )

    expires_at = datetime.fromisoformat(
        contact["verification_expires_at"]
    )

    if datetime.now(timezone.utc) > expires_at:

        supabase.table("emergency_contacts").update({
            "status": "expired"
        }).eq("id", request_id).execute()

        raise HTTPException(
            status_code=400,
            detail="Code expiré."
        )

    # WRONG CODE
    if request.verification_code != contact["verification_code"]:

        supabase.table("emergency_contacts").update({
            "failed_attempts":
                contact["failed_attempts"] + 1
        }).eq("id", request_id).execute()

        raise HTTPException(
            status_code=400,
            detail="Code invalide."
        )

    # ACCEPT
    supabase.table("emergency_contacts").update({

        "status": "accepted",
        "verification_code": None,
        "verification_expires_at": None,
        "failed_attempts": 0

    }).eq("id", request_id).execute()

    return {
        "success": True,
        "message": "Contact confirmé."
    }

# =========================
# MY CONTACTS
# =========================

@router.get("/my-contacts")
def my_contacts(
    current_user=Depends(get_current_user)
):

    get_user_profile(current_user["user_id"])

    response = (
        supabase.table("emergency_contacts")
        .select("*")
        .eq("requester_id", current_user["user_id"])
        .eq("status", "accepted")
        .execute()
    )

    return {
        "contacts": response.data
    }