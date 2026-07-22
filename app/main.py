from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

from .routes import (
    routes,
    tracking,
    auth,
    notifications,
    emergency_contacts,
    profile
)

app = FastAPI()
security = HTTPBearer()
limiter = Limiter(
    key_func=get_remote_address
)

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