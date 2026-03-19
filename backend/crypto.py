import logging

from cryptography.fernet import Fernet

from backend.config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.encryption_key
        if isinstance(key, str):
            key = key.encode()
        _fernet = Fernet(key)
    return _fernet


def encrypt(value: str) -> str:
    try:
        encrypted = _get_fernet().encrypt(value.encode()).decode()
        logger.debug("Value encrypted successfully")
        return encrypted
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise


def decrypt(value: str) -> str:
    try:
        decrypted = _get_fernet().decrypt(value.encode()).decode()
        logger.debug("Value decrypted successfully")
        return decrypted
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise
