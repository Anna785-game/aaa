from fastapi import Header, HTTPException
from .database import supabase


def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token manquant")

    try: 
        token = authorization.split(" ")[1]

        user_response = supabase.auth.get_user(token)

        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token invalide")

        user = user_response.user

        return {
            "user_id": user.id,
            "email": user.email
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")