"""Secret storage for SMTP credentials.

Secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using a key that
is read from ``EMAIL_ENCRYPTION_KEY``. The key is never stored in the database
or in the repository.

``EMAIL_ENCRYPTION_KEY`` may be either a standard Fernet key produced by
``Fernet.generate_key()`` or a long random passphrase. A passphrase is hashed
with SHA-256 before use, so operators are not forced to handle base64.

Development fallback: when no key is configured and ``DEBUG`` is true, a key is
derived from ``DJANGO_SECRET_KEY`` so local development keeps working. This
fallback is intentionally rejected in production.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class SecretStorageError(Exception):
    """Raised when a secret cannot be encrypted or decrypted."""


def _configured_key():
    return (getattr(settings, "EMAIL_ENCRYPTION_KEY", "") or "").strip()


def _build_fernet(raw_key: str) -> Fernet:
    candidate = raw_key.strip()
    if not candidate:
        raise SecretStorageError("No email encryption key is configured.")
    try:
        return Fernet(candidate.encode())
    except (ValueError, TypeError):
        # Treat non-Fernet values as a passphrase and derive a valid key.
        digest = hashlib.sha256(candidate.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> Fernet:
    raw_key = _configured_key()
    if raw_key:
        return _build_fernet(raw_key)
    if getattr(settings, "DEBUG", False):
        # Local-only fallback. Production requires a dedicated key.
        return _build_fernet(settings.SECRET_KEY)
    raise SecretStorageError(
        "EMAIL_ENCRYPTION_KEY is not configured. Add a strong key to the "
        "server environment before saving SMTP credentials."
    )


def encryption_key_configured() -> bool:
    """Return True when a dedicated key exists (or the DEBUG fallback is used)."""
    return bool(_configured_key()) or bool(getattr(settings, "DEBUG", False))


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    except SecretStorageError:
        raise
    except Exception as exc:  # Never leak the value in the error.
        raise SecretStorageError("The SMTP password could not be encrypted.") from exc


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretStorageError(
            "The saved SMTP password could not be decrypted. Check "
            "EMAIL_ENCRYPTION_KEY, or enter the password again."
        ) from exc
    except SecretStorageError:
        raise
    except Exception as exc:
        raise SecretStorageError(
            "The saved SMTP password could not be decrypted."
        ) from exc


def mask_secret(value: str = "") -> str:
    """Return a display-safe placeholder. Never includes any secret characters."""
    return "••••••••" if value else "Not set"
