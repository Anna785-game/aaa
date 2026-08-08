#main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

from .limiter import limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

from .routes import (
    routes,
    tracking,
    auth,
    notifications,
    emergency_contacts,
    profile,
    admin
)

app = FastAPI()
security = HTTPBearer()

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler
)

app.add_middleware(SlowAPIMiddleware)

# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://musical-beijinho-6a1081.netlify.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ROUTERS
# =========================

app.include_router(routes.router)
app.include_router(tracking.router)
app.include_router(auth.router)
app.include_router(notifications.router)
app.include_router(emergency_contacts.router)
app.include_router(profile.router)
app.include_router(admin.router)

# =========================
# STATIC FILES
# =========================

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

# =========================
# HOME
# =========================

@app.get("/")
def home():
    return {
        "status": "Safe Route Tracker API running"
    }

# =========================
# OPENAPI / JWT
# =========================

PUBLIC_PATHS = [
    "/",
    "/auth/login",
    "/auth/register",
]

def custom_openapi():

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Safe Route Tracker",
        version="1.0.0",
        description="API with JWT auth",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    for path in openapi_schema["paths"]:

        if path not in PUBLIC_PATHS:

            for method in openapi_schema["paths"][path]:

                openapi_schema["paths"][path][method]["security"] = [
                    {"BearerAuth": []}
                ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


logger = logging.getLogger("global_errors")
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erreur non gérée sur {request.url}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
    )

