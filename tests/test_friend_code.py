from warestore.domain.accounts.friend_code import (
    cs2_friend_code,
    friend_code_for_steamid,
)


def test_known_vector():
    # Gabe Newell's account — the canonical published friend code.
    assert cs2_friend_code(76561197960287930) == "SUCVS-FADA"


def test_format_is_two_dash_separated_groups():
    code = cs2_friend_code(76561198034202275)
    head, sep, tail = code.partition("-")
    assert sep == "-"
    assert len(head) == 5 and len(tail) == 4
    assert set(code) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789-")


def test_deterministic():
    assert cs2_friend_code(76561198034202275) == cs2_friend_code(76561198034202275)


def test_for_steamid_accepts_valid_string():
    assert friend_code_for_steamid("76561197960287930") == "SUCVS-FADA"


def test_for_steamid_rejects_junk():
    assert friend_code_for_steamid("") == ""
    assert friend_code_for_steamid("not-a-number") == ""
    assert friend_code_for_steamid("123") == ""  # below the SteamID64 base
    assert friend_code_for_steamid(None) == ""  # type: ignore[arg-type]
