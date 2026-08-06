#tracking.py

from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Header,
    HTTPException,
    Query
)
from ..dependencies import get_current_user
from ..schemas import TrackSegmentRequest, ResumeTrackingRequest

from ..limiter import limiter
from ..services.tracking.tracking_service import (
    start_new_session,
    upload_tracking_segment,
    resume_session,
    complete_session,
    get_history,
    get_session_history_detail,
    delete_history_session, 
    get_history_stats_service,
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
    x_current_accuracy: Annotated[str, Header(alias="x-current-accuracy")] = None,

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

    # La précision est optionnelle : si absente ou invalide, on continue
    # sans elle (tolérance de base appliquée côté service).
    current_accuracy = None
    if x_current_accuracy:
        try:
            current_accuracy = float(x_current_accuracy.strip())
            if current_accuracy < 0:
                current_accuracy = None
        except ValueError:
            current_accuracy = None

    return start_new_session(
        route_id=route_id,
        user_id=current_user["user_id"],
        device_id=device_id.strip(),
        current_lat=current_lat,
        current_lng=current_lng,
        current_accuracy=current_accuracy
    )


# =========================
# UPLOAD SEGMENT
# =========================

@router.post("/segment/{session_id}")
@limiter.limit("20/minute")
def upload_segment(
    request: Request,
    session_id: str,
    payload: TrackSegmentRequest,
    current_user=Depends(get_current_user)
):
    return upload_tracking_segment(
        session_id,
        payload,
        current_user["user_id"]
    )

# =========================
# RESUME SESSION
# =========================

@router.post("/resume/{session_id}")
@limiter.limit("10/minute")
def resume_tracking(
    request: Request,
    session_id: str,
    payload: ResumeTrackingRequest,
    current_user=Depends(get_current_user)
):
    return resume_session(
        session_id,
        payload,
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
    

# =========================
# SESSION HISTORIQUE
# =========================

@router.get("/history")
def tracking_history(
    route_id: Optional[str] = Query(None),
    has_alerts: Optional[bool] = Query(None),
    from_date: Optional[str] = Query(None, description="ISO date, ex: 2026-07-01"),
    to_date: Optional[str] = Query(None, description="ISO date, ex: 2026-08-01"),
    current_user=Depends(get_current_user)
):
    return {
        "history": get_history(
            current_user["user_id"],
            route_id=route_id,
            has_alerts=has_alerts,
            from_date=from_date,
            to_date=to_date
        )
    }


@router.get("/history/{session_id}")
def tracking_history_detail(
    session_id: str,
    current_user=Depends(get_current_user)
):
    return get_session_history_detail(session_id, current_user["user_id"])


@router.delete("/history/{session_id}")
@limiter.limit("10/minute")
def delete_tracking_history(
    request: Request,
    session_id: str,
    current_user=Depends(get_current_user)
):
    return delete_history_session(session_id, current_user["user_id"])

@router.get("/history/stats")
def tracking_history_stats(
    route_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="ISO date, ex: 2026-07-01"),
    to_date: Optional[str] = Query(None, description="ISO date, ex: 2026-08-01"),
    current_user=Depends(get_current_user)
):
    return {
        "stats": get_history_stats_service(
            current_user["user_id"],
            route_id=route_id,
            from_date=from_date,
            to_date=to_date
        )
    }