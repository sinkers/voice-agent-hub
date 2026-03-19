import os


def _get_encryption_key() -> str:
    key = os.getenv("HUB_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "HUB_ENCRYPTION_KEY must be set in environment. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'"
        )
    return key


class Settings:
    encryption_key: str = _get_encryption_key()
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////data/hub.db")
    hub_secret: str = os.getenv("HUB_SECRET", "change-me-in-production")
    base_url: str = os.getenv("BASE_URL", "http://localhost:8080")
    livekit_agents: list[str] = [
        a.strip()
        for a in os.getenv("LIVEKIT_AGENTS", "").split(",")
        if a.strip()
    ]
    cors_origins: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "*").split(",")
        if o.strip()
    ]


settings = Settings()
