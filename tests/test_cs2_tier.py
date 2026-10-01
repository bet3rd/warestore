from warestore.domain.accounts.cs2_tier import (
    NON_PRIME,
    PREMIER,
    PREMIER_READY,
    PRIME,
    UNKNOWN,
    cs2_tier,
)


def test_premier_rating_wins_over_everything():
    assert cs2_tier(prime=-1, level=-1, premier_rating=12_480) == PREMIER


def test_prime_level_ten_is_premier_ready():
    assert cs2_tier(prime=1, level=10, premier_rating=-1) == PREMIER_READY


def test_prime_below_ten_is_prime():
    assert cs2_tier(prime=1, level=9, premier_rating=-1) == PRIME
    assert cs2_tier(prime=1, level=-1, premier_rating=-1) == PRIME


def test_non_prime():
    assert cs2_tier(prime=0, level=25, premier_rating=-1) == NON_PRIME


def test_unknown_when_prime_never_read():
    assert cs2_tier(prime=-1, level=25, premier_rating=-1) == UNKNOWN
