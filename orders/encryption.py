"""Field-level encryption helper for sensitive data at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` library.
The encryption key is read from ``settings.FIELD_ENCRYPTION_KEY``.

The field is **backwards compatible** with rows that contain plain text
(legacy data written before encryption was enabled): if Fernet decryption
fails, the value is returned as-is so reads keep working. The next save
re-encrypts the row.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


def _is_testing() -> bool:
    import sys
    return "test" in sys.argv or any("pytest" in a for a in sys.argv)


def _derived_key() -> bytes:
    """Return a Fernet key.

    Priority:
      1. ``settings.FIELD_ENCRYPTION_KEY`` (must be a 44-char urlsafe base64 string).
      2. In ``DEBUG`` o durante tests, derivar una llave estable desde
         ``SECRET_KEY`` para no obligar a configurarla en cada entorno local.

    En producción, fallar al iniciar cuando la llave no está configurada es
    intencional — no queremos cifrar silenciosamente con un default débil.
    """
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if key:
        return key.encode() if isinstance(key, str) else key
    if getattr(settings, "DEBUG", False) or _is_testing():
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        return base64.urlsafe_b64encode(digest)
    raise ImproperlyConfigured(
        "FIELD_ENCRYPTION_KEY no configurada. Genera una con:\n"
        "    python -c 'from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())'\n"
        "y agrégala a tu .env."
    )


_fernet_cache: Fernet | None = None


def _fernet() -> Fernet:
    global _fernet_cache
    if _fernet_cache is None:
        _fernet_cache = Fernet(_derived_key())
    return _fernet_cache


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")


class EncryptedTextField(models.TextField):
    """TextField that transparently encrypts on write and decrypts on read.

    Reads of legacy plain-text rows continue to work; the next save
    re-stores the value as ciphertext.
    """

    description = "Encrypted text (Fernet)"

    def from_db_value(self, value, expression, connection):  # type: ignore[override]
        if value is None or value == "":
            return value
        try:
            return decrypt_text(value)
        except (InvalidToken, ValueError):
            # Legacy plain text or corrupted ciphertext; surface raw value.
            return value

    def to_python(self, value):  # type: ignore[override]
        if value is None or value == "":
            return value
        # Heuristic: Fernet tokens always start with "gAAAAA" (version byte).
        if isinstance(value, str) and value.startswith("gAAAAA"):
            try:
                return decrypt_text(value)
            except (InvalidToken, ValueError):
                return value
        return value

    def get_prep_value(self, value):  # type: ignore[override]
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            value = str(value)
        # Avoid double-encryption if the value is already a token.
        if value.startswith("gAAAAA"):
            try:
                decrypt_text(value)
                return value
            except (InvalidToken, ValueError):
                pass
        return encrypt_text(value)
