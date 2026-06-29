from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "A Trading System API"
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )
    auto_tushare_refresh_enabled: bool = os.getenv("AUTO_TUSHARE_REFRESH_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    auto_tushare_refresh_hour: int = int(os.getenv("AUTO_TUSHARE_REFRESH_HOUR", "2"))
    auto_tushare_refresh_minute: int = int(os.getenv("AUTO_TUSHARE_REFRESH_MINUTE", "30"))


settings = Settings()
