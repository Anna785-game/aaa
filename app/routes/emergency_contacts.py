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

from ..schemas import (
    EmergencyContactCreate,
    EmergencyContactUpdate
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
            detail="Profil requis avant d'utiliser cette fonctionnalité."
        )

    return response.data[0]


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

    # LIMITE COÛT SMS : max 3 contacts actifs
    count_res = (
        supabase.table("emergency_contacts")
        .select("id", count="exact")
        .eq("requester_id", current_user["user_id"])
        .eq("status", "active")
        .execute()
    )
    if (count_res.count or 0) >= 3:
        raise HTTPException(
            status_code=400,
            detail="Maximum 3 contacts d'urgence autorisés."
        )

    response = supabase.table("emergency_contacts").insert({
        "requester_id": current_user["user_id"],
        "target_full_name": full_name,
        "target_phone_number": phone_number,
        "relationship": payload.relationship,
        "status": "active"
    }).execute()

    return {
        "success": True,
        "message": "Contact ajouté.",
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
# UPDATE CONTACT
# =========================

@router.put("/{contact_id}")
@limiter.limit("10/minute")
def update_emergency_contact(
    request: Request,
    contact_id: str,
    payload: EmergencyContactUpdate,
    current_user=Depends(get_current_user)
):
    requester_profile = get_user_profile(current_user["user_id"])

    # Vérifie que le contact existe et appartient à l'utilisateur
    existing = (
        supabase.table("emergency_contacts")
        .select("*")
        .eq("id", contact_id)
        .eq("requester_id", current_user["user_id"])
        .eq("status", "active")
        .execute()
    )

    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail="Contact introuvable."
        )

    current_contact = existing.data[0]
    updates = {}

    # --- Nom ---
    if payload.full_name is not None:
        name = payload.full_name.strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail="Le nom ne peut pas être vide."
            )
        updates["target_full_name"] = name

    # --- Téléphone ---
    if payload.phone_number is not None:
        phone = payload.phone_number.strip()
        if not phone:
            raise HTTPException(
                status_code=400,
                detail="Le numéro de téléphone ne peut pas être vide."
            )

        # Interdit de mettre son propre numéro
        if phone == requester_profile["phone_number"]:
            raise HTTPException(
                status_code=400,
                detail="Impossible de s'ajouter soi-même."
            )

        # Vérifie unicité seulement si le numéro change
        if phone != current_contact["target_phone_number"]:
            phone_taken = (
                supabase.table("emergency_contacts")
                .select("id")
                .eq("requester_id", current_user["user_id"])
                .eq("target_phone_number", phone)
                .neq("id", contact_id)
                .execute()
            )
            if phone_taken.data:
                raise HTTPException(
                    status_code=400,
                    detail="Ce numéro est déjà utilisé pour un autre contact."
                )

        updates["target_phone_number"] = phone

    # --- Relation ---
    if payload.relationship is not None:
        updates["relationship"] = payload.relationship

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Aucune modification fournie."
        )

    response = (
        supabase.table("emergency_contacts")
        .update(updates)
        .eq("id", contact_id)
        .eq("requester_id", current_user["user_id"])
        .execute()
    )

    return {
        "success": True,
        "message": "Contact mis à jour.",
        "contact": response.data[0] if response.data else None
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