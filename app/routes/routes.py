import uuid
from fastapi import APIRouter, Depends, HTTPException
from ..database import supabase
from ..schemas import RouteCreate
from ..dependencies import get_current_user

router = APIRouter(prefix="/routes", tags=["Routes"])


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


# Optionnel : Récupérer les détails d'une route
@router.get("/{route_id}")
def get_route_details(route_id: str, current_user=Depends(get_current_user)):
    response = supabase.table("routes") \
        .select("id, route_name, is_sensitive, created_at") \
        .eq("id", route_id) \
        .eq("user_id", current_user["user_id"]) \
        .execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Route introuvable")

    return {
        "success": True,
        "route": response.data[0]
    }