from dataclasses import asdict

from fastapi import APIRouter

from app.services.data_asset_service import DataAssetService

router = APIRouter(prefix="/data-assets", tags=["data-assets"])


@router.get("/stocks/summary")
def get_stock_data_asset_summary() -> dict:
    return asdict(DataAssetService().get_stock_data_asset_summary())


@router.post("/stocks/refresh")
def request_stock_data_asset_refresh() -> dict:
    return asdict(DataAssetService().request_stock_data_asset_refresh())
