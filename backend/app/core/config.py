from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "A Trading System API"
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )


settings = Settings()
