"""Fernet symmetric encryption for broker credentials at rest.

Key is loaded from BROKER_CRED_SECRET (a URL-safe base64 Fernet key). We
construct the Fernet instance eagerly at import time so a missing or malformed
key fails loudly on startup rather than silently at first auth attempt.

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

try:
    _fernet = Fernet(settings.broker_cred_secret.encode())
except Exception as exc:
    raise RuntimeError(
        "BROKER_CRED_SECRET is missing or not a valid Fernet key. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    ) from exc


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
