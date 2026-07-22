from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from ..database import supabase

from ..dependencies import (
    get_current_user
)

from ..schemas import (
    ProfileCreate
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
            request.phone_number
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