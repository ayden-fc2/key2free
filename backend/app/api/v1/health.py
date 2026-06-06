from fastapi import APIRouter

from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> dict[str, str]:
    return HealthService().get_health()

