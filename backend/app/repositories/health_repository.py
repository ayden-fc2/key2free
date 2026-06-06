from datetime import datetime, timezone


class HealthRepository:
    def get_health(self) -> dict[str, str]:
        return {
            "status": "ok",
            "service": "backend",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

