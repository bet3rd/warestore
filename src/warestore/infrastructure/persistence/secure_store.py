# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Encrypted JSON store for sensitive data at rest (saved tokens).

Two modes:
  * DPAPI (default): bound to the current Windows user — a copied file is useless
    elsewhere, but local same-user code can still decrypt it.
  * Master password: AES-256-GCM with a PBKDF2-derived key (see `vault_crypto`).
    Adds a secret only the user knows, on top of the at-rest protection.

The mode is decided by whether a `key` is provided. On read the on-disk format
is auto-detected, and a file in the "wrong" format is transparently re-saved in
the active mode — so enabling/disabling the password, or upgrading from a legacy
plaintext file, never strands data.
"""

import json
import logging
import os
from typing import Any

import win32crypt

from warestore.infrastructure.persistence import vault_crypto

logger = logging.getLogger(__name__)

# Fixed app-level entropy; ties the DPAPI blob to WareStore + the Windows user.
_ENTROPY = b"warestore-vault-v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class SecureStoreUnavailable(Exception):
    """The store exists but could not be decrypted/read (locked vault, bad blob,
    unreadable file). Distinct from a genuinely empty/absent store — callers that
    must fail closed (e.g. irreversible deletes) treat this as "unknown", not
    "no data"."""


def _protect(raw: bytes) -> bytes:
    blob = win32crypt.CryptProtectData(
        raw, "warestore vault", _ENTROPY, None, None, _CRYPTPROTECT_UI_FORBIDDEN
    )
    return blob[0] if isinstance(blob, (tuple, list)) else blob


def _unprotect(blob: bytes) -> bytes:
    _desc, plaintext = win32crypt.CryptUnprotectData(blob, _ENTROPY, None, None, 0)
    return plaintext


class SecureJsonStore:
    """A JSON document encrypted at rest (DPAPI, or AES when a key is set)."""

    def __init__(self, path: str, key: bytes | None = None) -> None:
        self._path = path
        self._key = key

    def set_key(self, key: bytes | None) -> None:
        self._key = key

    def read(
        self, default: dict[str, Any] | None = None, *, strict: bool = False
    ) -> dict[str, Any]:
        """Decrypt and return the stored document.

        A missing/empty file returns the default (genuinely no data). When
        `strict` is set, a store that exists but cannot be read/decrypted raises
        `SecureStoreUnavailable` instead of silently falling back to the default,
        so safety-critical callers can tell "no data" apart from "unavailable".
        """

        def _unavailable(reason: str) -> dict[str, Any]:
            if strict:
                raise SecureStoreUnavailable(f"{os.path.basename(self._path)}: {reason}")
            return dict(default or {})

        try:
            with open(self._path, "rb") as f:
                blob = f.read()
        except FileNotFoundError:
            return dict(default or {})
        except OSError as exc:
            logger.warning(f"Could not read {self._path}: {exc}")
            return _unavailable(str(exc))

        if not blob.strip():
            return dict(default or {})

        # AES vault (master password).
        if vault_crypto.is_vault_blob(blob):
            if self._key is None:
                logger.error(f"{os.path.basename(self._path)} is password-protected but locked.")
                return _unavailable("password-protected but locked")
            try:
                return json.loads(vault_crypto.decrypt(self._key, blob).decode("utf-8"))
            except Exception as exc:
                logger.error(f"Vault decrypt failed for {self._path}: {exc}")
                return _unavailable(f"decrypt failed: {exc}")

        # Legacy plaintext JSON → migrate into the active mode.
        try:
            data = json.loads(blob.decode("utf-8"))
            logger.info(f"Migrating plaintext {os.path.basename(self._path)} to encrypted vault.")
            self.write(data)
            return data
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

        # DPAPI blob.
        try:
            data = json.loads(_unprotect(blob).decode("utf-8"))
        except Exception as exc:
            logger.error(f"Vault decrypt failed for {self._path}: {exc}")
            return _unavailable(f"decrypt failed: {exc}")
        if self._key is not None:
            # Password mode now active but file is DPAPI → upgrade to AES.
            logger.info(f"Upgrading {os.path.basename(self._path)} to password-encrypted vault.")
            self.write(data)
        return data

    def write(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        raw = json.dumps(data, indent=2).encode("utf-8")
        blob = vault_crypto.encrypt(self._key, raw) if self._key is not None else _protect(raw)
        with open(self._path, "wb") as f:
            f.write(blob)
