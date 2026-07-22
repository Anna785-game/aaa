from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Header,
    HTTPException
)

from ..dependencies import get_current_user
from ..schemas import TrackSegmentRequest, ResumeTrackingRequest

from ..main import limiter
from ..services.tracking.tracking_service import (
    start_new_session,
    upload_tracking_segment,
    resume_session,
    complete_session
)

router = APIRouter(
    prefix="/tracking",
    tags=["Tracking"]
)


# =========================
# START TRACKING (Version Anti-Voleur)
# =========================

@router.post("/start/{route_id}")
@limiter.limit("10/minute")
def start_tracking(
    request: Request,
    route_id: str,
    current_user=Depends(get_current_user),

    # Headers pour la position actuelle (obligatoires)
    x_current_lat: Annotated[str, Header(alias="x-current-lat")] = None,
    x_current_lng: Annotated[str, Header(alias="x-current-lng")] = None,

    # Device ID
    device_id: Annotated[
        str,
        Header(..., min_length=8, alias="device-id")
    ] = None
):
    if not device_id or not device_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Device ID invalide."
        )

    if not x_current_lat or not x_current_lng:
        raise HTTPException(
            status_code=400,
            detail="Position actuelle (latitude et longitude) requise via headers."
        )

    try:
        current_lat = float(x_current_lat.strip())
        current_lng = float(x_current_lng.strip())
        
        # Validation basique des coordonnées
        if not (-90 <= current_lat <= 90) or not (-180 <= current_lng <= 180):
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Coordonnées GPS invalides."
        )

    return start_new_session(
        route_id=route_id,
        user_id=current_user["user_id"],
        device_id=device_id.strip(),
        current_lat=current_lat,
        current_lng=current_lng
    )


# =========================
# UPLOAD SEGMENT
# =========================

@router.post("/segment/{session_id}")
@limiter.limit("20/minute")
def upload_segment(
    request_http: Request,
    session_id: str,
    request: TrackSegmentRequest,
    current_user=Depends(get_current_user)
):
    return upload_tracking_segment(
        session_id,
        request,
        current_user["user_id"]
    )


# =========================
# RESUME SESSION
# =========================

@router.post("/resume/{session_id}")
@limiter.limit("10/minute")
def resume_tracking(
    request_http: Request,
    session_id: str,
    request: ResumeTrackingRequest,
    current_user=Depends(get_current_user)
):
    return resume_session(
        session_id,
        request,
        current_user["user_id"]
    )


# =========================
# COMPLETE SESSION
# =========================

@router.post("/complete/{session_id}")
@limiter.limit("10/minute")
def complete_tracking(
    request: Request,
    session_id: str,
    current_user=Depends(get_current_user)
):
    return complete_session(
        session_id,
        current_user["user_id"]
    )