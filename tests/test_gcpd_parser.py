from warestore.infrastructure.steam.gcpd_parser import (
    COOLDOWN_PERMANENT,
    looks_like_gcpd_page,
    looks_like_login_page,
    parse_matchmaking,
)

NOW = 1_700_000_000  # fixed "now" for deterministic cooldown comparisons
FUTURE = "2099-01-01 12:00:00 GMT"
PAST = "2000-01-01 12:00:00 GMT"


def _kv(rows: str) -> str:
    return f'<table class="generic_kv_table">{rows}</table>'


RANKS = (
    "<tr><th>Matchmaking Mode</th><th>Wins</th><th>Ties</th><th>Losses</th>"
    "<th>Skill Group</th><th>Last Match</th><th>Region</th></tr>"
    "<tr><td>Premier</td><td>1,234</td><td>0</td><td>1,000</td><td>18,567</td><td>x</td><td>EU</td></tr>"
    "<tr><td>Wingman</td><td>56</td><td>0</td><td>40</td><td>12</td><td>x</td><td>EU</td></tr>"
)


def test_active_cooldown_and_ranks():
    html = (
        _kv(f"<tr><th>Cooldown Expiration</th><th>Level</th><th>Ack</th></tr>"
            f"<tr><td>{FUTURE}</td><td>1</td><td>Yes</td></tr>")
        + _kv(RANKS)
    )
    r = parse_matchmaking(html, now=NOW)
    assert r.premier_rating == 18567 and r.premier_wins == 1234
    assert r.wingman_rank == 12 and r.wingman_wins == 56
    assert r.cooldown_expires_unix > NOW and r.cooldown_reason == "Competitive cooldown"


def test_permanent_cooldown():
    html = _kv("<tr><th>Cooldown</th><th>Level</th><th>Ack</th></tr>"
               "<tr><td>Never</td><td>7</td><td>No</td></tr>") + _kv(RANKS)
    r = parse_matchmaking(html, now=NOW)
    assert r.cooldown_expires_unix == COOLDOWN_PERMANENT
    assert r.premier_rating == 18567  # ranks still parsed


def test_expired_cooldown_is_none():
    html = _kv(f"<tr><th>Cooldown</th><th>Level</th><th>Ack</th></tr>"
               f"<tr><td>{PAST}</td><td>1</td><td>Yes</td></tr>") + _kv(RANKS)
    r = parse_matchmaking(html, now=NOW)
    assert r.cooldown_expires_unix == 0 and r.cooldown_reason == ""


def test_per_map_table_is_skipped():
    html = (
        _kv("<tr><th>Matchmaking Mode</th><th>Map</th><th>Wins</th><th>Skill Group</th></tr>"
            "<tr><td>Premier</td><td>de_dust2</td><td>99</td><td>99999</td></tr>")
        + _kv(RANKS)
    )
    r = parse_matchmaking(html, now=NOW)
    assert r.premier_rating == 18567  # from the real table, not the 99999 decoy


def test_unranked_blanks_stay_unknown():
    html = _kv(
        "<tr><th>Matchmaking Mode</th><th>Wins</th><th>Ties</th><th>Losses</th>"
        "<th>Skill Group</th><th>Last Match</th><th>Region</th></tr>"
        "<tr><td>Premier</td><td>0</td><td>0</td><td>0</td><td>&nbsp</td><td>x</td><td>3</td></tr>"
        "<tr><td>Wingman</td><td>48</td><td>0</td><td>40</td><td>&nbsp</td><td>x</td><td>3</td></tr>"
    )
    r = parse_matchmaking(html, now=NOW)
    assert r.premier_rating == -1 and r.wingman_rank == -1  # blank skill -> unknown
    assert r.premier_wins == 0 and r.wingman_wins == 48     # wins still read


def test_page_signatures():
    assert looks_like_gcpd_page(_kv(RANKS))
    assert looks_like_login_page("<html><title>Sign In</title>g_steamID = false;</html>")
    assert not looks_like_gcpd_page("<html><title>Sign In</title></html>")
