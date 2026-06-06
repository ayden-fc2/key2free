from app.repositories.health_repository import HealthRepository


class HealthService:
    def __init__(self) -> None:
        self.repository = HealthRepository()

    def get_health(self) -> dict[str, str]:
        return self.repository.get_health()

