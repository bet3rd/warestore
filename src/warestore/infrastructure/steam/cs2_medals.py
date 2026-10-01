# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Names and icons for CS2 profile medals (service medals, coins, pins).

The CS2 server only gives each medal's item id (def_index). Names and image
URLs come from the public ByMykel/CSGO-API dataset, whose images are on
Steam's own CDN. Both are cached under the app's data folder: the catalog is
refreshed weekly (or daily while a medal id is missing from it), and each icon
is downloaded once at 64x64.

``ensure`` does network I/O — call it off the Qt thread (the account check
does). ``display``/``name``/``icon_path`` only read the cache. Failures are
swallowed: a missing icon falls back to the medal's name.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

from warestore.config.settings import ACCOUNT_MANAGER_DATA_DIR

logger = logging.getLogger(__name__)

CATALOG_URL = (
    "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/collectibles.json"
)
CACHE_DIR = os.path.join(ACCOUNT_MANAGER_DATA_DIR, "cache", "cs2_medals")
ICON_SIZE = "64fx64f"  # Steam economy-image size suffix
_REFRESH_AGE = 7 * 86_400
_MISSING_RETRY_AGE = 86_400
_TIMEOUT = 20


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, path: str) -> bool:
    tmp = path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp, open(tmp, "wb") as f:
        f.write(resp.read())
    os.replace(tmp, path)
    return True


class MedalCatalog:
    def __init__(self, cache_dir: str = CACHE_DIR, *, fetch=_fetch_json, download=_download,
                 now=time.time) -> None:
        self._dir = cache_dir
        self._fetch = fetch
        self._download = download
        self._now = now
        self._cache: dict | None = None

    # --- cache-only reads (safe on the Qt thread) ------------------------------

    def name(self, def_index: int) -> str:
        item = self._items().get(str(def_index))
        return item["name"] if item else f"Medal {def_index}"

    def icon_path(self, def_index: int) -> str | None:
        path = self._icon_file(def_index)
        return path if os.path.exists(path) else None

    def display(self, def_indexes) -> list[tuple[str, str | None]]:
        """(name, cached icon path or None) per medal, in the given order."""
        return [(self.name(i), self.icon_path(i)) for i in def_indexes]

    # --- network (off the Qt thread) --------------------------------------------

    def ensure(self, def_indexes) -> None:
        """Make sure the catalog knows these medals and their icons are cached."""
        ids = [int(i) for i in def_indexes]
        if not ids:
            return
        try:
            self._refresh_if_needed(ids)
            items = self._items()
            os.makedirs(self._dir, exist_ok=True)
            for i in ids:
                item = items.get(str(i))
                if item and item.get("image") and not self.icon_path(i):
                    self._download(f"{item['image']}/{ICON_SIZE}", self._icon_file(i))
        except Exception as exc:  # noqa: BLE001 - icons are cosmetic; never fail a check
            logger.debug("medals: could not update icons: %s", exc)

    # --- internals ----------------------------------------------------------------

    def _catalog_file(self) -> str:
        return os.path.join(self._dir, "catalog.json")

    def _icon_file(self, def_index: int) -> str:
        return os.path.join(self._dir, f"{int(def_index)}.png")

    def _load(self) -> dict:
        if self._cache is None:
            try:
                with open(self._catalog_file(), encoding="utf-8") as f:
                    self._cache = json.load(f)
            except (OSError, ValueError):
                self._cache = {"fetched": 0, "items": {}}
        return self._cache

    def _items(self) -> dict:
        return self._load().get("items", {})

    def _refresh_if_needed(self, ids: list[int]) -> None:
        data = self._load()
        age = self._now() - data.get("fetched", 0)
        missing = any(str(i) not in data.get("items", {}) for i in ids)
        if age < _REFRESH_AGE and not (missing and age >= _MISSING_RETRY_AGE):
            return
        raw = self._fetch(CATALOG_URL)
        items = {}
        for entry in raw:
            try:
                key = str(int(entry["def_index"]))
            except (KeyError, TypeError, ValueError):
                continue
            items[key] = {"name": entry.get("name", ""), "image": entry.get("image", "")}
        self._cache = {"fetched": self._now(), "items": items}
        os.makedirs(self._dir, exist_ok=True)
        tmp = self._catalog_file() + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._cache, f)
        os.replace(tmp, self._catalog_file())
