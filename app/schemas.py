from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


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
    relationship: str


class EmergencyContactConfirm(BaseModel):
    verification_code: str