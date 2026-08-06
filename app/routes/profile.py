#profile.py
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request
)
from ..limiter import limiter

from ..database import supabase

from ..dependencies import (
    get_current_user
)

from ..schemas import (
    ProfileCreate,
    ProfileUpdate
)

router = APIRouter(
    prefix="/profile",
    tags=["Profile"]
)


# =========================
# CREATE PROFILE
# =========================

@router.post("/create")
def create_profile(
    request: ProfileCreate,
    current_user=Depends(get_current_user)
):

    # =========================
    # REQUIRED PHONE
    # =========================

    if not request.phone_number.strip():

        raise HTTPException(
            status_code=400,
            detail="Numéro de téléphone obligatoire."
        )

    # =========================
    # EXISTING PROFILE
    # =========================

    existing = (
        supabase.table("profiles")
        .select("*")
        .eq(
            "id",
            current_user["user_id"]
        )
        .execute()
    )

    if existing.data:

        raise HTTPException(
            status_code=400,
            detail="Profil déjà existant."
        )

    # =========================
    # PHONE ALREADY USED
    # =========================

    existing_phone = (
        supabase.table("profiles")
        .select("*")
        .eq(
            "phone_number",
            request.phone_number.strip()
        )
        .execute()
    )

    if existing_phone.data:

        raise HTTPException(
            status_code=400,
            detail="Numéro déjà utilisé."
        )

    # =========================
    # CREATE PROFILE
    # =========================

    response = (
        supabase.table("profiles")
        .insert({

            "id":
                current_user["user_id"],

            "full_name":
                request.full_name.strip(),

            "phone_number":
                request.phone_number.strip(),

            "age":
                request.age

        })
        .execute()
    )

    return {
        "success": True,
        "profile": response.data
    }


# =========================
# MY PROFILE
# =========================

@router.get("/me")
def my_profile(
    current_user=Depends(get_current_user)
):

    response = (
        supabase.table("profiles")
        .select("*")
        .eq(
            "id",
            current_user["user_id"]
        )
        .execute()
    )

    if not response.data:

        raise HTTPException(
            status_code=404,
            detail="Profil introuvable."
        )

    return {
        "profile": response.data[0]
    }


# =========================
# UPDATE PROFILE
# =========================

@router.put("/me")
@limiter.limit("10/minute")
def update_profile(
    request: Request,
    payload: ProfileUpdate,
    current_user=Depends(get_current_user)
):
    # Vérifie que le profil existe
    existing = (
        supabase.table("profiles")
        .select("*")
        .eq("id", current_user["user_id"])
        .execute()
    )

    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail="Profil introuvable."
        )

    current_profile = existing.data[0]
    updates = {}

    # --- Nom ---
    if payload.full_name is not None:
        name = payload.full_name.strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail="Le nom ne peut pas être vide."
            )
        updates["full_name"] = name

    # --- Téléphone ---
    if payload.phone_number is not None:
        phone = payload.phone_number.strip()
        if not phone:
            raise HTTPException(
                status_code=400,
                detail="Le numéro de téléphone ne peut pas être vide."
            )

        # Vérifie unicité uniquement si le numéro change
        if phone != current_profile["phone_number"]:
            phone_taken = (
                supabase.table("profiles")
                .select("id")
                .eq("phone_number", phone)
                .neq("id", current_user["user_id"])
                .execute()
            )
            if phone_taken.data:
                raise HTTPException(
                    status_code=400,
                    detail="Numéro déjà utilisé."
                )

        updates["phone_number"] = phone

    # --- Âge ---
    if payload.age is not None:
        updates["age"] = payload.age

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Aucune modification fournie."
        )

    response = (
        supabase.table("profiles")
        .update(updates)
        .eq("id", current_user["user_id"])
        .execute()
    )

    return {
        "success": True,
        "profile": response.data[0] if response.data else None
    }


# =========================
# DELETE PROFILE
# =========================

@router.delete("/me")
@limiter.limit("5/minute")
def delete_profile(
    request: Request,
    current_user=Depends(get_current_user)
):
    """
    Supprime uniquement la ligne dans `profiles`.
    Le compte auth (email/password) reste intact.
    L'utilisateur pourra recréer un profil plus tard.
    """
    response = (
        supabase.table("profiles")
        .delete()
        .eq("id", current_user["user_id"])
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail="Profil introuvable."
        )

    return {
        "success": True,
        "message": "Profil supprimé."
    }