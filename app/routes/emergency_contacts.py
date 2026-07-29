#emergency_contacts.py
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request
)
from ..limiter import limiter

from ..database import supabase
from ..dependencies import get_current_user

from ..schemas import EmergencyContactCreate

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
            detail="Profil requis avant d'utiliser cette fonctionnalité."
        )

    return response.data[0]


def find_linked_profile_id(phone_number: str):
    """Si le numéro correspond à un compte existant, on le lie (pour le push).
    Sinon target_id reste None (contact sans compte)."""

    response = (
        supabase.table("profiles")
        .select("id")
        .eq("phone_number", phone_number)
        .execute()
    )

    return response.data[0]["id"] if response.data else None

# =========================
# ADD CONTACT
# =========================

@router.post("/add")
@limiter.limit("5/minute")
def add_emergency_contact(
    request: Request,
    payload: EmergencyContactCreate,
    current_user=Depends(get_current_user)
):

    requester_profile = get_user_profile(current_user["user_id"])

    full_name = payload.full_name.strip()
    phone_number = payload.phone_number.strip()

    if not full_name or not phone_number:
        raise HTTPException(
            status_code=400,
            detail="Nom et téléphone du contact requis."
        )

    # BLOCK SELF ADD
    if phone_number == requester_profile["phone_number"]:
        raise HTTPException(
            status_code=400,
            detail="Impossible de s'ajouter soi-même."
        )

    # Lien optionnel vers un compte existant (permet le push plus tard)
    target_id = find_linked_profile_id(phone_number)

    # DÉDOUBLONNAGE
    existing = (
        supabase.table("emergency_contacts")
        .select("*")
        .eq("requester_id", current_user["user_id"])
        .eq("target_phone_number", phone_number)
        .execute()
    )

    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="Ce contact existe déjà."
        )

    response = supabase.table("emergency_contacts").insert({

        "requester_id": current_user["user_id"],
        "target_id": target_id,
        "target_full_name": full_name,
        "target_phone_number": phone_number,
        "relationship": payload.relationship,
        "status": "active"

    }).execute()

    return {
        "success": True,
        "message": "Contact ajouté.",
        "has_account": target_id is not None,
        "contact": response.data[0] if response.data else None
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
        .eq("status", "active")
        .execute()
    )

    return {
        "contacts": response.data
    }

# =========================
# DELETE CONTACT
# =========================

@router.delete("/{contact_id}")
def delete_contact(
    contact_id: str,
    current_user=Depends(get_current_user)
):

    response = (
        supabase.table("emergency_contacts")
        .delete()
        .eq("id", contact_id)
        .eq("requester_id", current_user["user_id"])
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail="Contact introuvable."
        )

    return {
        "success": True,
        "deleted": response.data
    }