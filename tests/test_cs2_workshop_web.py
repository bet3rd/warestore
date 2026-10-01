import io
import urllib.error

import pytest

from warestore.infrastructure.steam.cs2_workshop_web import (
    WorkshopSessionError,
    WorkshopWebClient,
    parse_subscription_page,
)

SID = 76561198000000001


def _page(ids, total):
    items = "".join(
        f'<a href="https://steamcommunity.com/sharedfiles/filedetails/?id={i}" class="ugc">'
        f'<div class="workshopItemPreviewHolder ">x</div></a>'
        for i in ids
    )
    return f"<div>Showing 1-30 of {total} entries</div>{items}"


class FakeResponse(io.BytesIO):
    def __init__(self, body: str, status=200):
        super().__init__(body.encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, pages=None, post_status=200, redirect=False):
        self.pages = pages or {}
        self.post_status = post_status
        self.redirect = redirect
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        if self.redirect:
            raise urllib.error.HTTPError(req.full_url, 302, "Found", {}, None)
        if req.get_method() == "POST":
            return FakeResponse("{}", self.post_status)
        page = int(req.full_url.rsplit("&p=", 1)[1].split("&", 1)[0])
        return FakeResponse(self.pages.get(page, _page([], 0)))


def test_parse_subscription_page():
    ids, total = parse_subscription_page(_page(["11", "22", "11"], 45))
    assert ids == ["11", "22"] and total == 45


def test_lists_every_page_until_total():
    opener = FakeOpener(pages={1: _page([str(i) for i in range(30)], 45),
                               2: _page([str(i) for i in range(30, 45)], 45)})
    client = WorkshopWebClient(SID, "tok", opener=opener, sleep=lambda s: None)
    assert client.list_subscriptions() == [str(i) for i in range(45)]


def test_clear_all_unsubscribes_each_item_with_matching_sessionid():
    opener = FakeOpener(pages={1: _page(["11", "22"], 2)})
    client = WorkshopWebClient(SID, "tok", opener=opener, sleep=lambda s: None)
    assert client.clear_all() == (2, 0)
    posts = [r for r in opener.requests if r.get_method() == "POST"]
    assert len(posts) == 2
    body = posts[0].data.decode()
    assert "appid=730" in body and "id=11" in body
    sessionid = body.split("sessionid=")[1]
    assert f"sessionid={sessionid}" in posts[0].get_header("Cookie")


def test_failed_unsubscribe_is_counted():
    opener = FakeOpener(pages={1: _page(["11"], 1)}, post_status=500)
    client = WorkshopWebClient(SID, "tok", opener=opener, sleep=lambda s: None)
    assert client.clear_all() == (0, 1)


def test_redirect_means_the_session_was_not_accepted():
    client = WorkshopWebClient(SID, "tok", opener=FakeOpener(redirect=True), sleep=lambda s: None)
    with pytest.raises(WorkshopSessionError):
        client.list_subscriptions()
