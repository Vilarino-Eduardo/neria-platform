import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.settings import get_settings


def get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.credential_encryption_key
    if key is None:
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
        ).decode("ascii")
    return Fernet(key.encode("ascii"))


def encrypt_secret(value: str) -> str:
    return get_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    return get_fernet().decrypt(value.encode("ascii")).decode("utf-8")
