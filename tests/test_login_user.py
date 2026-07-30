from warestore.domain.steam.models import LoginUser


def test_login_user_to_dict():
    user = LoginUser(
        steam_id="76561198000000001",
        account_name="alice",
        persona_name="Alice",
        timestamp=123,
        most_recent="1",
    )
    d = user.to_dict()
    assert d["steamid"] == "76561198000000001"
    assert d["account_name"] == "alice"
    assert d["most_recent"] == "1"
