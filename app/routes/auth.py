from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from ..main import limiter

from ..database import supabase
from ..schemas import UserAuth

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/register")
@limiter.limit("3/minute")
def register(
    request: Request,
    user: UserAuth
):

    try:

        response = supabase.auth.sign_up({
            "email": user.email,
            "password": user.password
        })

        return {
            "success": True,
            "user": response.user
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    user: UserAuth
):

    try:

        response = supabase.auth.sign_in_with_password({
            "email": user.email,
            "password": user.password
        })

        return {
            "success": True,
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": response.user
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )