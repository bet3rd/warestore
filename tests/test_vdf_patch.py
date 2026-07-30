from pathlib import Path

import pytest

from warestore.domain.steam.services.vdf_patcher import VdfPatcher

FIXTURES = Path(__file__).parent / "fixtures"
SID_A = "76561198000000001"
SID_B = "76561198000000002"


@pytest.fixture
def patcher() -> VdfPatcher:
    return VdfPatcher()


@pytest.fixture
def loginusers_text() -> str:
    return (FIXTURES / "loginusers_multi.vdf").read_text(encoding="utf-8")


@pytest.fixture
def local_vdf_text() -> str:
    return (FIXTURES / "local_connectcache.vdf").read_text(encoding="utf-8")


def test_patch_user_fields_only_touches_target(patcher: VdfPatcher, loginusers_text: str):
    out = patcher.patch_user_fields(
        loginusers_text,
        SID_B,
        {"AllowAutoLogin": "0", "RememberPassword": "0"},
    )
    assert '"76561198000000001"' in out
    alice_slice = out.split('"76561198000000001"')[1].split('"76561198000000002"')[0]
    bob_slice = out.split('"76561198000000002"')[1]
    assert '"AllowAutoLogin"\t\t"0"' in bob_slice
    assert '"RememberPassword"\t\t"0"' in bob_slice
    assert '"AllowAutoLogin"\t\t"1"' in alice_slice
    assert '"TokenGUID"' in out


def test_global_patch_field_would_break_other_users(patcher: VdfPatcher, loginusers_text: str):
    """Regression: old switch_account used patch_field globally."""
    out = patcher.patch_field(loginusers_text, "AllowAutoLogin", "0")
    assert out.count('"AllowAutoLogin"\t\t"0"') == 2


def test_set_most_recent(patcher: VdfPatcher, loginusers_text: str):
    out = patcher.set_most_recent(loginusers_text, SID_B)
    a = out.split(f'"{SID_A}"')[1].split(f'"{SID_B}"')[0]
    b = out.split(f'"{SID_B}"')[1]
    assert '"MostRecent"\t\t"0"' in a
    assert '"MostRecent"\t\t"1"' in b


def test_merge_loginuser_entry_preserves_token_guid(patcher: VdfPatcher):
    users = {
        SID_A: {
            "AccountName": "alice",
            "TokenGUID": "{keep-me}",
            "MostRecent": "0",
        },
        SID_B: {"AccountName": "bob", "MostRecent": "1"},
    }
    patcher.merge_loginuser_entry(users, SID_A, "alice_new", timestamp="999")
    assert users[SID_A]["TokenGUID"] == "{keep-me}"
    assert users[SID_A]["AccountName"] == "alice_new"
    assert users[SID_A]["MostRecent"] == "1"
    assert users[SID_B]["MostRecent"] == "0"


def test_append_loginuser_block(patcher: VdfPatcher, loginusers_text: str):
    new_sid = "76561198000000099"
    out = patcher.append_loginuser_block(loginusers_text, new_sid, "charlie", "1700000099")
    assert f'"{new_sid}"' in out
    assert '"AccountName"\t\t"charlie"' in out
    assert '"76561198000000001"' in out


def test_patch_connect_cache_updates_existing_key(patcher: VdfPatcher, local_vdf_text: str):
    out = patcher.patch_connect_cache(local_vdf_text, "abc1231", "newhex")
    assert '"abc1231"\t\t"newhex"' in out
    assert '"def4561"\t\t"cafebabe"' in out


def test_patch_connect_cache_inserts_new_key(patcher: VdfPatcher, local_vdf_text: str):
    out = patcher.patch_connect_cache(local_vdf_text, "9999991", "added")
    assert '"9999991"\t\t"added"' in out
    assert '"def4561"\t\t"cafebabe"' in out
