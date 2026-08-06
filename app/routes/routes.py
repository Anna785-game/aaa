#routes.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from ..limiter import limiter
from ..database import supabase
from ..schemas import RouteCreate, RouteUpdate, RoutePointsUpdate
from ..dependencies import get_current_user

router = APIRouter(prefix="/routes", tags=["Routes"])


# =========================
# CREATE
# =========================

@router.post("/create")
def create_route(route: RouteCreate, current_user=Depends(get_current_user)):
    route_id = str(uuid.uuid4())

    try:
        # 1. Création de la route
        supabase.table("routes").insert({
            "id": route_id,
            "user_id": current_user["user_id"],
            "route_name": route.route_name.strip(),
            "is_sensitive": route.is_sensitive
        }).execute()

        # 2. Insertion des points (Bulk Insert)
        if route.points:
            points_to_insert = [
                {
                    "route_id": route_id,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "order_index": i
                }
                for i, p in enumerate(route.points)
            ]

            if points_to_insert:
                supabase.table("route_points").insert(points_to_insert).execute()

        return {
            "success": True,
            "route_id": route_id,
            "is_sensitive": route.is_sensitive
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la création de la route : {str(e)}"
        )


# =========================
# LIST
# =========================

@router.get("/list")
def list_routes(current_user=Depends(get_current_user)):
    response = supabase.table("routes") \
        .select("id, route_name, is_sensitive, created_at") \
        .eq("user_id", current_user["user_id"]) \
        .order("created_at", desc=True) \
        .execute()

    return {
        "success": True,
        "routes": [
            {
                "id": r["id"],
                "name": r["route_name"],
                "is_sensitive": r.get("is_sensitive", False),
                "created_at": r.get("created_at")
            }
            for r in response.data
        ]
    }


# =========================
# DETAILS (avec points)
# =========================

@router.get("/{route_id}")
def get_route_details(route_id: str, current_user=Depends(get_current_user)):
    response = supabase.table("routes") \
        .select("id, route_name, is_sensitive, created_at") \
        .eq("id", route_id) \
        .eq("user_id", current_user["user_id"]) \
        .execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Route introuvable")

    route = response.data[0]

    points_resp = supabase.table("route_points") \
        .select("latitude, longitude, order_index") \
        .eq("route_id", route_id) \
        .order("order_index") \
        .execute()

    return {
        "success": True,
        "route": {
            **route,
            "points": points_resp.data or []
        }
    }


# =========================
# UPDATE (nom + sensible)
# =========================

@router.put("/{route_id}")
@limiter.limit("10/minute")
def update_route(
    request: Request,
    route_id: str,
    payload: RouteUpdate,
    current_user=Depends(get_current_user)
):
    # Vérifie existence + propriété
    existing = supabase.table("routes") \
        .select("id") \
        .eq("id", route_id) \
        .eq("user_id", current_user["user_id"]) \
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Route introuvable")

    updates = {}

    if payload.route_name is not None:
        name = payload.route_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Le nom ne peut pas être vide.")
        updates["route_name"] = name

    if payload.is_sensitive is not None:
        updates["is_sensitive"] = payload.is_sensitive

    if not updates:
        raise HTTPException(status_code=400, detail="Aucune modification fournie.")

    response = supabase.table("routes") \
        .update(updates) \
        .eq("id", route_id) \
        .eq("user_id", current_user["user_id"]) \
        .execute()

    return {
        "success": True,
        "route": response.data[0] if response.data else None
    }


# =========================
# REPLACE POINTS (remplacement complet)
# =========================

@router.put("/{route_id}/points")
@limiter.limit("10/minute")
def replace_route_points(
    request: Request,
    route_id: str,
    payload: RoutePointsUpdate,
    current_user=Depends(get_current_user)
):
    if not payload.points or len(payload.points) < 2:
        raise HTTPException(
            status_code=400,
            detail="Une route doit contenir au moins 2 points GPS."
        )

    # Vérifie existence + propriété
    existing = supabase.table("routes") \
        .select("id") \
        .eq("id", route_id) \
        .eq("user_id", current_user["user_id"]) \
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Route introuvable")

    try:
        # 1. Supprime tous les anciens points
        supabase.table("route_points") \
            .delete() \
            .eq("route_id", route_id) \
            .execute()

        # 2. Insère les nouveaux points
        points_to_insert = [
            {
                "route_id": route_id,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "order_index": i
            }
            for i, p in enumerate(payload.points)
        ]

        supabase.table("route_points").insert(points_to_insert).execute()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la mise à jour des points : {str(e)}"
        )

    return {
        "success": True,
        "message": "Points de la route remplacés.",
        "points_count": len(payload.points)
    }


# =========================
# DELETE
# =========================

@router.delete("/{route_id}")
@limiter.limit("5/minute")
def delete_route(
    request: Request,
    route_id: str,
    current_user=Depends(get_current_user)
):
    """
    Supprime la route.
    Grâce aux ON DELETE CASCADE :
    - route_points → supprimés
    - tracking_sessions liées → supprimées
    - tracking_segments + alerts → supprimés en cascade
    """
    response = supabase.table("routes") \
        .delete() \
        .eq("id", route_id) \
        .eq("user_id", current_user["user_id"]) \
        .execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Route introuvable")

    return {
        "success": True,
        "message": "Route et données associées supprimées.",
        "deleted": response.data
    }


# =========================
# REVERSE (trajet retour)
# =========================

@router.post("/{route_id}/reverse")
def reverse_route(route_id: str, current_user=Depends(get_current_user)):
    route_resp = supabase.table("routes") \
        .select("*") \
        .eq("id", route_id) \
        .eq("user_id", current_user["user_id"]) \
        .execute()

    if not route_resp.data:
        raise HTTPException(status_code=404, detail="Route introuvable")

    route = route_resp.data[0]

    points_resp = supabase.table("route_points") \
        .select("*") \
        .eq("route_id", route_id) \
        .order("order_index") \
        .execute()

    points = points_resp.data
    if not points:
        raise HTTPException(status_code=400, detail="Cette route ne contient aucun point.")

    # Nom auto : "Maison → École" devient "École → Maison"
    name = route["route_name"]
    if " → " in name:
        new_name = " → ".join(reversed(name.split(" → ")))
    else:
        new_name = f"{name} (retour)"

    new_route_id = str(uuid.uuid4())

    try:
        supabase.table("routes").insert({
            "id": new_route_id,
            "user_id": current_user["user_id"],
            "route_name": new_name,
            "is_sensitive": route.get("is_sensitive", False)
        }).execute()

        reversed_points = list(reversed(points))
        points_to_insert = [
            {
                "route_id": new_route_id,
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "order_index": i
            }
            for i, p in enumerate(reversed_points)
        ]
        supabase.table("route_points").insert(points_to_insert).execute()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'inversion de la route : {str(e)}"
        )

    return {
        "success": True,
        "route_id": new_route_id,
        "route_name": new_name
    }