from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class CredentialError(ValueError):
    pass


def _fernet() -> Fernet:
    value = settings.ACCOUNT_CREDENTIAL_KEY.strip()
    if not value:
        raise ImproperlyConfigured("ACCOUNT_CREDENTIAL_KEY is required to manage credentials")
    try:
        return Fernet(value.encode("ascii"))
    except (ValueError, TypeError) as error:
        raise ImproperlyConfigured("ACCOUNT_CREDENTIAL_KEY must be a valid Fernet key") from error


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise CredentialError("The encrypted credential cannot be decrypted") from error
