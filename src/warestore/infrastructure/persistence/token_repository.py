# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os
import time
from typing import Any

from warestore.config.settings import ACCOUNT_MANAGER_DATA_DIR
from warestore.infrastructure.persistence.secure_store import SecureJsonStore


class TokenRepository:
    def __init__(self, path: str | None = None, key: bytes | None = None) -> None:
        # Tokens are refresh-token JWTs: encrypted at rest (DPAPI, or AES when a
        # master-password key is supplied).
        self._store = SecureJsonStore(
            path or os.path.join(ACCOUNT_MANAGER_DATA_DIR, "tokens.json"), key=key
        )

    def load_all(self) -> dict[str, dict[str, Any]]:
        return self._store.read()

    def load_all_strict(self) -> dict[str, dict[str, Any]]:
        """Like `load_all`, but raises `SecureStoreUnavailable` if the token file
        exists yet can't be decrypted (locked vault, bad blob). For callers that
        must not mistake "couldn't read tokens" for "no tokens"."""
        return self._store.read(strict=True)

    def save_all(self, tokens: dict[str, dict[str, Any]]) -> None:
        self._store.write(tokens)

    def rekey(self, new_key: bytes | None) -> None:
        """Re-encrypt the token file from the current key to `new_key`."""
        data = self.load_all()
        self._store.set_key(new_key)
        self.save_all(data)

    def store(self, steam_id: str, username: str, token: str) -> None:
        saved = self.load_all()
        saved[steam_id] = {"username": username, "token": token, "ts": time.time()}
        self.save_all(saved)

    def remove(self, steam_id: str) -> bool:
        saved = self.load_all()
        if steam_id not in saved:
            return False
        del saved[steam_id]
        self.save_all(saved)
        return True
