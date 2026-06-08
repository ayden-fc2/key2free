from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.backtests import router as backtests_router
from app.api.v1.data_assets import router as data_assets_router
from app.api.v1.health import router as health_router
from app.api.v1.signals import router as signals_router
from app.core.config import settings


fastapi_app = FastAPI(title=settings.app_name)

fastapi_app.include_router(health_router, prefix="/api/v1")
fastapi_app.include_router(data_assets_router, prefix="/api/v1")
fastapi_app.include_router(signals_router, prefix="/api/v1")
fastapi_app.include_router(backtests_router, prefix="/api/v1")

app = CORSMiddleware(
    fastapi_app,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
