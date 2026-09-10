from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import check_database_connection
from app.routes.auth import router as auth_router
from app.routes.dain import router as dain_router
from app.db.base import Base
from app.db.session import engine, is_sqlite
import app.models as _models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-create tables and seed categories when running locally on SQLite."""
    if is_sqlite:
        Base.metadata.create_all(bind=engine)
        try:
            from app.db.seed import seed
            seed()
        except Exception:
            pass
    yield


app = FastAPI(
    title="DAIN API",
    version="0.1.0",
    description="Backend foundation for the DUNITE Achievement & Impact Network.",
    lifespan=lifespan,
)


origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(auth_router)

app.include_router(dain_router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "message": "DAIN backend is running",
        "status": "ok",
    }


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report whether the API process and its PostgreSQL connection are available."""
    check_database_connection()
    return {
        "status": "ok",
        "environment": settings.app_env,
    }
    
