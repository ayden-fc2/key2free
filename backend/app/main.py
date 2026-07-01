from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.backtests import router as backtests_router
from app.api.v1.health import router as health_router
from app.api.v1.signals import router as signals_router
from app.api.v1.tushare_assets import router as tushare_assets_router
from app.core.config import settings
from app.repositories.backtest_repository import BacktestRepository
from app.services.tushare_auto_refresh_scheduler import TushareAutoRefreshScheduler
from app.services.tushare_asset_service import TushareAssetService


fastapi_app = FastAPI(title=settings.app_name)


@fastapi_app.on_event("startup")
def clear_stale_running_tasks() -> None:
    BacktestRepository().finish_running_tasks(
        "backend startup found a stale running backtest task and marked it as error.",
    )
    TushareAssetService().finish_stale_running_tasks(
        "backend startup found a stale running Tushare refresh task and marked it as error.",
    )
    TushareAutoRefreshScheduler.start()


@fastapi_app.on_event("shutdown")
def stop_auto_refresh_scheduler() -> None:
    TushareAutoRefreshScheduler.stop()


fastapi_app.include_router(health_router, prefix="/api/v1")
fastapi_app.include_router(tushare_assets_router, prefix="/api/v1")
fastapi_app.include_router(signals_router, prefix="/api/v1")
fastapi_app.include_router(backtests_router, prefix="/api/v1")

app = CORSMiddleware(
    fastapi_app,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
