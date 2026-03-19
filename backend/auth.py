import logging
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from backend.config import settings

logger = logging.getLogger(__name__)

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
    token = jwt.encode(payload, settings.hub_secret, algorithm=ALGORITHM)
    logger.info(f"Created session token for user {user_id[:8]}...")
    return token


def decode_session_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.hub_secret, algorithms=[ALGORITHM])
        logger.debug(f"Decoded session token for user {payload.get('sub', 'unknown')[:8]}...")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token validation failed: expired")
        raise
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token validation failed: {e}")
        raise
