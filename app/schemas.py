#schemas.py

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

# Relations autorisées (alignées avec le CHECK de la base)
ALLOWED_RELATIONSHIPS = Literal[
    "mother",
    "father",
    "brother",
    "sister",
    "guardian",
    "uncle",
    "aunt",
    "grandmother",
    "grandfather",
    "spouse",      # conjoint(e)
    "partner",     # partenaire / compagnon
    "friend",      # ami(e)
    "cousin",
    "other"
]

class GPSPoint(BaseModel):
    latitude: float = Field(
        ge=-90,
        le=90
    )
    longitude: float = Field(
        ge=-180,
        le=180
    )
    timestamp: Optional[datetime] = None
    interpolated: bool = False


class RouteCreate(BaseModel):
    route_name: str
    points: List[GPSPoint]
    is_sensitive: bool = False   # ← Important pour la protection anti-vol


class TrackSegmentRequest(BaseModel):
    points: List[GPSPoint]


class ResumeTrackingRequest(BaseModel):
    latitude: float
    longitude: float


class UserAuth(BaseModel):
    email: str
    password: str
    
    
class DeviceTokenRegister(BaseModel):
    token: str
    platform: str
    
    
class ProfileCreate(BaseModel):
    full_name: str
    phone_number: str
    age: int


class EmergencyContactCreate(BaseModel):
    full_name: str
    phone_number: str
    relationship: ALLOWED_RELATIONSHIPS

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0, le=120)
    
class EmergencyContactUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    relationship: Optional[ALLOWED_RELATIONSHIPS] = None
    
class RouteUpdate(BaseModel):
    route_name: Optional[str] = None
    is_sensitive: Optional[bool] = None


class RoutePointsUpdate(BaseModel):
    points: List[GPSPoint]