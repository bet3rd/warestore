import os

from warestore.config.settings import STEAMID64_BASE
from warestore.infrastructure.steam.userdata_gateway import UserdataGateway


def _id64(id32: int) -> str:
    return str(id32 + STEAMID64_BASE)


def _make_account(steam_dir: str, id32: str, *, size: int = 0, cs2: bool = False) -> str:
    path = os.path.join(steam_dir, "userdata", id32)
    os.makedirs(path, exist_ok=True)
    if size:
        with open(os.path.join(path, "blob.bin"), "wb") as f:
            f.write(b"\0" * size)
    if cs2:
        os.makedirs(os.path.join(path, "730"), exist_ok=True)
    return path


def test_folders_in_login_list_are_not_candidates(tmp_path):
    steam = str(tmp_path)
    _make_account(steam, "111")
    _make_account(steam, "222")

    found = UserdataGateway().scan(steam, {_id64(111)}, set())

    assert [f.account_id32 for f in found] == ["222"]


def test_token_managed_folders_are_flagged_not_hidden(tmp_path):
    # The safety-critical case: an account absent from loginusers.vdf but still
    # logged in via a saved token must be surfaced as token_managed, so the UI
    # can keep it out of the default delete.
    steam = str(tmp_path)
    _make_account(steam, "111")
    _make_account(steam, "222")

    found = UserdataGateway().scan(steam, set(), {_id64(111)})
    by_id = {f.account_id32: f for f in found}

    assert by_id["111"].token_managed is True
    assert by_id["222"].token_managed is False


def test_reports_size_and_cs2_config(tmp_path):
    steam = str(tmp_path)
    _make_account(steam, "111", size=2048, cs2=True)

    found = UserdataGateway().scan(steam, set(), set())

    assert found[0].size_bytes >= 2048
    assert found[0].has_cs2_config is True


def test_skips_shared_zero_folder_and_non_numeric(tmp_path):
    # userdata/0 is Steam's anonymous/shared store, never a real account.
    steam = str(tmp_path)
    _make_account(steam, "0")
    os.makedirs(os.path.join(steam, "userdata", "notanid"), exist_ok=True)
    _make_account(steam, "333")

    found = UserdataGateway().scan(steam, set(), set())

    assert [f.account_id32 for f in found] == ["333"]


def test_sorted_largest_first(tmp_path):
    steam = str(tmp_path)
    _make_account(steam, "111", size=100)
    _make_account(steam, "222", size=9000)

    found = UserdataGateway().scan(steam, set(), set())

    assert [f.account_id32 for f in found] == ["222", "111"]


def test_missing_userdata_dir_is_empty(tmp_path):
    assert UserdataGateway().scan(str(tmp_path), set(), set()) == []


def test_delete_removes_folders_and_reports_freed(tmp_path):
    steam = str(tmp_path)
    _make_account(steam, "111", size=1024)
    _make_account(steam, "222", size=1024)
    gw = UserdataGateway()
    found = gw.scan(steam, set(), set())

    count, freed, errors = gw.delete(found)

    assert count == 2
    assert freed >= 2048
    assert errors == []
    assert not os.path.exists(os.path.join(steam, "userdata", "111"))
    assert not os.path.exists(os.path.join(steam, "userdata", "222"))


def test_delete_continues_past_failures(tmp_path):
    steam = str(tmp_path)
    _make_account(steam, "111", size=512)
    gw = UserdataGateway()
    found = gw.scan(steam, set(), set())
    # Point one entry at a path that no longer exists.
    ghost = found[0].__class__(
        account_id32="999",
        path=os.path.join(steam, "userdata", "999"),
        size_bytes=0,
        token_managed=False,
        has_cs2_config=False,
    )

    count, _freed, errors = gw.delete([ghost, *found])

    assert count == 1  # the real one still got removed
    assert len(errors) == 1
    assert not os.path.exists(os.path.join(steam, "userdata", "111"))
