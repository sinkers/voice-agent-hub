import secrets
from datetime import UTC, datetime, timedelta

import jwt

from backend.config import settings

DEVICE_CODE_EXPIRES = timedelta(seconds=900)
SESSION_TOKEN_EXPIRES = timedelta(days=30)
ALGORITHM = "HS256"


def generate_device_code() -> str:
    return secrets.token_hex(16)


def device_code_expiry() -> datetime:
    return datetime.now(UTC) + DEVICE_CODE_EXPIRES


def create_session_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(UTC) + SESSION_TOKEN_EXPIRES,
    }
    return jwt.encode(payload, settings.hub_secret, algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict:
    return jwt.decode(token, settings.hub_secret, algorithms=[ALGORITHM])
