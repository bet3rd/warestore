import json
import os

from warestore.infrastructure.steam.cs2_medals import MedalCatalog

DAY = 86_400
RAW = [
    {"id": "collectible-874", "def_index": "874", "name": "5 Year Veteran Coin",
     "image": "https://cdn.example/coin"},
    {"id": "collectible-4951", "def_index": 4951, "name": "2025 Service Medal",
     "image": "https://cdn.example/medal"},
    {"id": "collectible-x", "name": "no def index", "image": "https://cdn.example/x"},
]


class Net:
    def __init__(self):
        self.catalog_fetches = 0
        self.downloads = []

    def fetch(self, url):
        self.catalog_fetches += 1
        return RAW

    def download(self, url, path):
        self.downloads.append(url)
        with open(path, "wb") as f:
            f.write(b"png")
        return True


def _catalog(tmp_path, net, now=1_000_000):
    clock = {"now": now}
    cat = MedalCatalog(str(tmp_path), fetch=net.fetch, download=net.download, now=lambda: clock["now"])
    return cat, clock


def test_ensure_fetches_the_catalog_and_64px_icons_once(tmp_path):
    net = Net()
    cat, _ = _catalog(tmp_path, net)
    cat.ensure([874, 4951])
    cat.ensure([874, 4951])
    assert net.catalog_fetches == 1
    assert net.downloads == ["https://cdn.example/coin/64fx64f", "https://cdn.example/medal/64fx64f"]
    assert cat.name(4951) == "2025 Service Medal"
    assert os.path.exists(cat.icon_path(874))


def test_display_offline_uses_only_the_cache(tmp_path):
    net = Net()
    cat, _ = _catalog(tmp_path, net)
    cat.ensure([874])
    fresh = MedalCatalog(str(tmp_path), fetch=lambda u: 1 / 0, download=lambda u, p: 1 / 0)
    assert fresh.display([874, 4951, 99]) == [
        ("5 Year Veteran Coin", cat.icon_path(874)),
        ("2025 Service Medal", None),  # known, icon not downloaded yet
        ("Medal 99", None),            # unknown id
    ]


def test_stale_catalog_is_refreshed_weekly(tmp_path):
    net = Net()
    cat, clock = _catalog(tmp_path, net)
    cat.ensure([874])
    clock["now"] += 8 * DAY
    cat.ensure([874])
    assert net.catalog_fetches == 2


def test_unknown_id_refetches_at_most_daily(tmp_path):
    net = Net()
    cat, clock = _catalog(tmp_path, net)
    cat.ensure([874])
    cat.ensure([12345])  # a brand-new medal the catalog doesn't have yet
    assert net.catalog_fetches == 1
    clock["now"] += 2 * DAY
    cat.ensure([12345])
    assert net.catalog_fetches == 2


def test_network_failure_never_raises(tmp_path):
    def boom(*_a):
        raise OSError("offline")

    cat = MedalCatalog(str(tmp_path), fetch=boom, download=boom, now=lambda: 0)
    cat.ensure([874])
    assert cat.display([874]) == [("Medal 874", None)]


def test_catalog_is_stored_compact(tmp_path):
    net = Net()
    cat, _ = _catalog(tmp_path, net)
    cat.ensure([874])
    stored = json.load(open(os.path.join(str(tmp_path), "catalog.json"), encoding="utf-8"))
    assert stored["items"]["874"] == {"name": "5 Year Veteran Coin", "image": "https://cdn.example/coin"}
