import pytest

from warestore.infrastructure.steam import cs2_gc_proto as gp

ACCT = 39_734_273  # synthetic account id
OTHER = 12_345


def test_varint_roundtrip_through_fields():
    payload = gp.encode_varint((1 << 3) | 0) + gp.encode_varint(300)
    assert list(gp.iter_fields(payload)) == [(1, 0, 300)]


def test_iter_fields_rejects_truncated_input():
    with pytest.raises(ValueError):
        list(gp.iter_fields(b"\x0a\x05ab"))  # length 5, only 2 bytes


def test_client_hello_carries_version():
    fields = {num: v for num, _w, v in gp.iter_fields(gp.encode_client_hello())}
    assert fields[1] == gp.GC_CLIENT_VERSION


def test_parse_loadout_reads_both_object_types_and_ignores_others():
    welcome = gp.encode_welcome(
        [
            (3, gp.encode_equip_slot_object(ACCT, gp.TEAM_T, 4, 64)),        # T pistol 3 = R8
            (43, gp.encode_default_equipped_object(ACCT, gp.TEAM_CT, 2, 61)),  # CT start = USP-S
            (3, gp.encode_equip_slot_object(OTHER, gp.TEAM_T, 3, 2)),        # someone else's
            (3, gp.encode_equip_slot_object(ACCT, gp.TEAM_T, 1, 42)),        # knife slot: not a weapon slot
        ],
        version=77,
    )
    assert gp.parse_loadout(welcome, ACCT) == {(gp.TEAM_T, 4): 64, (gp.TEAM_CT, 2): 61}
    assert gp.so_cache_version(welcome) == 77


def test_parse_loadout_skips_a_malformed_object():
    welcome = gp.encode_welcome([(3, b"\xff"), (3, gp.encode_equip_slot_object(ACCT, gp.TEAM_T, 4, 64))])
    assert gp.parse_loadout(welcome, ACCT) == {(gp.TEAM_T, 4): 64}


def test_resolve_loadout_fills_defaults_for_all_30_slots():
    resolved = gp.resolve_loadout({(gp.TEAM_T, 4): 64})
    assert len(resolved) == 30
    assert resolved[(gp.TEAM_T, 4)] == 64
    assert resolved[(gp.TEAM_CT, 15)] == 60  # default M4A1-S


def test_equip_message_encodes_default_item_ids_and_change_num():
    body = gp.encode_adjust_equip_slots([(gp.TEAM_T, 4, 64)], change_num=78)
    fields = list(gp.iter_fields(body))
    slot = {n: v for n, _w, v in gp.iter_fields(fields[0][2])}
    assert slot == {1: gp.TEAM_T, 2: 4, 3: 0xF000000000000000 | 64}
    assert fields[-1][:1] == (2,) and fields[-1][2] == 78


def test_decode_players_profile_reads_level_and_premier():
    me = gp.encode_account_profile(ACCT, level=6, premier_rating=12_345, premier_wins=41)
    other = gp.encode_account_profile(OTHER, level=30)
    prof = gp.decode_players_profile(gp.encode_players_profile([other, me]), ACCT)
    assert prof == gp.GcProfile(account_id=ACCT, level=6, premier_rating=12_345, premier_wins=41)


def test_unranked_premier_is_minus_one():
    prof = gp.decode_account_profile(gp.encode_account_profile(ACCT, level=6, premier_rating=0, premier_wins=0))
    assert prof.premier_rating == -1


def test_negative_cooldown_seconds_mean_no_cooldown():
    # The GC sends "seconds remaining" as a signed int; an expired cooldown is negative.
    prof = gp.decode_account_profile(gp.encode_account_profile(ACCT, cooldown_seconds=-3600))
    assert prof.cooldown_seconds == 0
    prof = gp.decode_account_profile(gp.encode_account_profile(ACCT, cooldown_seconds=7200))
    assert prof.cooldown_seconds == 7200


def test_players_profile_without_entries_is_none():
    assert gp.decode_players_profile(b"", ACCT) is None


def _game_account(**fields):
    return b"".join(gp._vfield(num, value) for num, value in fields.items())


def test_decode_prime_from_elevated_state():
    prime = gp.encode_welcome([(gp.SO_TYPE_GAME_ACCOUNT, gp._vfield(1, 0) + gp._vfield(12, 1) + gp._vfield(14, 5))])
    assert gp.decode_prime(prime) is True


def test_decode_prime_missing_elevated_state_is_non_prime():
    non_prime = gp.encode_welcome([(gp.SO_TYPE_GAME_ACCOUNT, gp._vfield(1, 0) + gp._vfield(12, 1))])
    assert gp.decode_prime(non_prime) is False


def test_decode_prime_unknown_without_game_account_object():
    other = gp.encode_welcome([(gp.SO_TYPE_EQUIP_SLOT, gp.encode_equip_slot_object(ACCT, 2, 2, 61))])
    assert gp.decode_prime(other) is None
    assert gp.decode_prime(b"") is None


def test_account_profile_carries_the_penalty_reason():
    buf = gp._vfield(1, ACCT) + gp._vfield(4, 600) + gp._vfield(5, 10)
    prof = gp.decode_account_profile(buf)
    assert prof.cooldown_seconds == 600 and prof.penalty_reason == 10
