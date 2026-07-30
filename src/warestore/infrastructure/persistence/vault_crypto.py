# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Vault crypto: envelope encryption with PBKDF2-HMAC-SHA256 + AES-256-GCM.

The token file is encrypted with a random data key (DEK). The DEK is wrapped
separately by a key derived from the master password and by one derived from a
one-time recovery code, so either can unlock it, and changing the password just
re-wraps the DEK (no re-encrypting tokens).

Blob layout (token file and wraps): MAGIC(4) | nonce(12) | ciphertext+tag.
"""

import base64
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"WSV1"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16
NONCE_BYTES = 12
DEK_BYTES = 32
RECOVERY_BYTES = 20  # 160 bits → 32 base32 chars


def new_salt() -> bytes:
    return os.urandom(SALT_BYTES)


def new_dek() -> bytes:
    return secrets.token_bytes(DEK_BYTES)


def derive_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(password.encode("utf-8"))


def is_vault_blob(blob: bytes) -> bool:
    return blob[: len(MAGIC)] == MAGIC


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def decrypt(key: bytes, blob: bytes) -> bytes:
    if not is_vault_blob(blob):
        raise ValueError("not a WSV1 vault blob")
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_BYTES]
    ciphertext = blob[len(MAGIC) + NONCE_BYTES :]
    return AESGCM(key).decrypt(nonce, ciphertext, None)


# --- DEK wrapping (envelope) ---


def wrap_dek(kek: bytes, dek: bytes) -> str:
    """Encrypt the DEK with a key-encryption key; returns hex for settings."""
    return encrypt(kek, dek).hex()


def unwrap_dek(kek: bytes, wrapped_hex: str) -> bytes:
    """Recover the DEK; raises if the kek (wrong password/code) is invalid."""
    return decrypt(kek, bytes.fromhex(wrapped_hex))


# --- recovery code ---


def generate_recovery_code() -> str:
    """A high-entropy, transcribable code, e.g. ABCD-EFGH-... (base32, 160 bits)."""
    b32 = base64.b32encode(secrets.token_bytes(RECOVERY_BYTES)).decode("ascii").rstrip("=")
    return "-".join(b32[i : i + 4] for i in range(0, len(b32), 4))


def normalize_recovery_code(code: str) -> str:
    """Strip formatting (dashes/spaces/case) so input matches the stored form."""
    return "".join(ch for ch in code.upper() if ch.isalnum())
