# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd
# Approach ported from fakearchie/nfatool (MIT) — https://github.com/fakearchie/nfatool

"""List and remove an account's CS2 Workshop subscriptions on steamcommunity.

Uses the web access token minted over the account's own CM session. Redirects
are never followed: an expired/unaccepted session answers with a 3xx, and
following it could carry the cookie off-site.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_APP_ID = 730
_COMMUNITY = "https://steamcommunity.com"
_LIST_PATH = "/profiles/{sid}/myworkshopfiles/"
_LIST_QUERY = "?appid=730&browsefilter=mysubscriptions&numperpage=30&p={page}&l=english"
# A profile with a custom URL redirects /profiles/<id>/... to /id/<name>/...;
# that is the only redirect we follow.
_VANITY_PATH_RE = re.compile(r"^/id/[^/]+/myworkshopfiles/?$")
_UNSUB_URL = "https://steamcommunity.com/sharedfiles/unsubscribe"
_ID_RE = re.compile(r'filedetails/\?id=(\d+)"[^>]*><div class="workshopItemPreviewHolder')
_TOTAL_RE = re.compile(r"of ([\d,]+) entries")
_MAX_PAGES = 40
_PAGE_DELAY = 0.4
_UNSUB_DELAY = 0.15


class WorkshopSessionError(Exception):
    """steamcommunity redirected — the minted session was not accepted."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # urllib then raises HTTPError for the 3xx


def parse_subscription_page(html: str) -> tuple[list[str], int | None]:
    ids = list(dict.fromkeys(_ID_RE.findall(html)))
    total = _TOTAL_RE.search(html)
    return ids, int(total.group(1).replace(",", "")) if total else None


class WorkshopWebClient:
    def __init__(self, steamid: int, access_token: str, *, opener=None, sleep=time.sleep) -> None:
        self._steamid = steamid
        self._sessionid = secrets.token_hex(12)
        login = urllib.parse.quote(f"{steamid}||{access_token}", safe="")
        self._cookie = f"steamLoginSecure={login}; sessionid={self._sessionid}"
        self._opener = opener or urllib.request.build_opener(_NoRedirect)
        self._sleep = sleep

    def _open(self, req: urllib.request.Request):
        req.add_header("Cookie", self._cookie)
        req.add_header("User-Agent", "Mozilla/5.0")
        return self._opener.open(req, timeout=20)

    def _vanity_path(self, exc: urllib.error.HTTPError) -> str | None:
        """The /id/<name>/myworkshopfiles/ path a custom-URL profile redirects to,
        or None when the redirect goes anywhere else (e.g. a login page)."""
        location = urllib.parse.urlsplit((exc.headers or {}).get("Location", "") or "")
        if location.scheme == "https" and location.netloc == "steamcommunity.com" \
                and _VANITY_PATH_RE.match(location.path):
            return location.path.rstrip("/") + "/"
        return None

    def _fetch_page(self, path: str, page: int) -> tuple[str, str]:
        """(html, path) — the path changes once if the profile has a custom URL."""
        req = urllib.request.Request(_COMMUNITY + path + _LIST_QUERY.format(page=page))
        try:
            with self._open(req) as resp:
                return resp.read().decode("utf-8", "replace"), path
        except urllib.error.HTTPError as exc:
            if not 300 <= exc.code < 400:
                raise
            vanity = self._vanity_path(exc)
            if vanity is None or vanity == path:
                raise WorkshopSessionError("subscriptions page redirected") from exc
        return self._fetch_page(vanity, page)

    def list_subscriptions(self) -> list[str]:
        ids: list[str] = []
        path = _LIST_PATH.format(sid=self._steamid)
        for page in range(1, _MAX_PAGES + 1):
            html, path = self._fetch_page(path, page)
            page_ids, total = parse_subscription_page(html)
            new = [i for i in page_ids if i not in ids]
            ids.extend(new)
            if not new or total is None or len(ids) >= total:
                break
            self._sleep(_PAGE_DELAY)
        return ids

    def unsubscribe(self, file_id: str) -> bool:
        body = urllib.parse.urlencode({"appid": _APP_ID, "id": file_id, "sessionid": self._sessionid}).encode()
        req = urllib.request.Request(_UNSUB_URL, data=body, method="POST")
        try:
            with self._open(req) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, OSError) as exc:
            logger.debug("workshop: unsubscribe %s failed: %s", file_id, exc)
            return False

    def clear_all(self) -> tuple[int, int]:
        removed = failed = 0
        for file_id in self.list_subscriptions():
            if self.unsubscribe(file_id):
                removed += 1
            else:
                failed += 1
            self._sleep(_UNSUB_DELAY)
        logger.debug("workshop: %d unsubscribed, %d failed for %s", removed, failed, self._steamid)
        return removed, failed
