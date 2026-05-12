from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from geopy.distance import geodesic
from typing import List, Dict
from datetime import datetime
import uuid

app = FastAPI()

# =====================================================
# DATABASE SIMULÉE
# =====================================================

routes_db: Dict = {}
tracking_sessions: Dict = {}

# =====================================================
# CONFIG
# =====================================================

DANGER_THRESHOLD = 200

# =====================================================
# MODELES
# =====================================================

class GPSPoint(BaseModel):
    latitude: float
    longitude: float


class RouteCreate(BaseModel):
    user_id: str
    route_name: str
    points: List[GPSPoint]


class TrackRequest(BaseModel):
    user_id: str
    latitude: float
    longitude: float


# =====================================================
# OUTILS
# =====================================================

def calculate_distance(p1, p2):

    return geodesic(p1, p2).meters


def find_closest_point(current_position, route_points):

    closest_distance = float("inf")
    closest_index = -1

    for i, point in enumerate(route_points):

        route_position = (
            point["latitude"],
            point["longitude"]
        )

        distance = calculate_distance(
            current_position,
            route_position
        )

        if distance < closest_distance:
            closest_distance = distance
            closest_index = i

    return {
        "distance": closest_distance,
        "index": closest_index
    }


# =====================================================
# CREER ROUTE
# =====================================================

@app.post("/routes/create")
def create_route(route: RouteCreate):

    route_id = str(uuid.uuid4())

    routes_db[route_id] = {
        "id": route_id,
        "user_id": route.user_id,
        "route_name": route.route_name,
        "points": [
            point.dict()
            for point in route.points
        ],
        "created_at": str(datetime.utcnow())
    }

    return {
        "success": True,
        "route_id": route_id
    }


# =====================================================
# VOIR ROUTES
# =====================================================

@app.get("/routes")
def get_routes():

    return routes_db


# =====================================================
# DEMARRER TRACKING
# =====================================================

@app.post("/tracking/start/{route_id}")
def start_tracking(
    route_id: str,
    request: TrackRequest
):

    if route_id not in routes_db:

        return {
            "success": False,
            "message": "Route introuvable"
        }

    session_id = str(uuid.uuid4())

    tracking_sessions[session_id] = {
        "session_id": session_id,
        "route_id": route_id,
        "user_id": request.user_id,
        "started_at": str(datetime.utcnow()),
        "alerts": []
    }

    return {
        "success": True,
        "session_id": session_id
    }


# =====================================================
# UPDATE POSITION
# =====================================================

@app.post("/tracking/update/{session_id}")
def update_tracking(
    session_id: str,
    request: TrackRequest
):

    if session_id not in tracking_sessions:

        return {
            "success": False,
            "message": "Session introuvable"
        }

    session = tracking_sessions[session_id]

    route = routes_db[session["route_id"]]

    current_position = (
        request.latitude,
        request.longitude
    )

    closest = find_closest_point(
        current_position,
        route["points"]
    )

    distance = closest["distance"]

    is_off_route = distance > DANGER_THRESHOLD

    response = {
        "success": True,
        "distance_from_route":
            round(distance, 2),
        "on_route": not is_off_route
    }

    if is_off_route:

        alert = {
            "type": "deviation",
            "time": str(datetime.utcnow()),
            "position": {
                "latitude": request.latitude,
                "longitude": request.longitude
            }
        }

        session["alerts"].append(alert)

        response["alert"] = (
            "ALERTE : déviation détectée"
        )

    return response


# =====================================================
# ALERTES
# =====================================================

@app.get("/tracking/alerts/{session_id}")
def get_alerts(session_id: str):

    if session_id not in tracking_sessions:

        return {
            "success": False
        }

    return {
        "success": True,
        "alerts":
            tracking_sessions[session_id]["alerts"]
    }


# =====================================================
# FRONTEND
# =====================================================

app.mount(
    "/",
    StaticFiles(directory="static", html=True),
    name="static"
)
