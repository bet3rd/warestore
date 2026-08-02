import base64
import json
import time

from warestore.domain.auth.jwt_service import SteamJwtService

SERVICE = SteamJwtService()
STEAM_ID = "76561198000000001"


def _fake_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b"{}").decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


def test_decode_steam_id():
    token = _fake_jwt({"sub": STEAM_ID})
    assert SERVICE.decode_steam_id(token) == STEAM_ID


def test_verify_steam_jwt_valid():
    token = _fake_jwt(
        {"iss": "steam", "aud": "client", "exp": int(time.time()) + 3600}
    )
    assert SERVICE.verify_expiry(token) > 0


def test_verify_steam_jwt_rejects_wrong_issuer():
    token = _fake_jwt({"iss": "other", "aud": "client", "exp": 9999999999})
    assert SERVICE.verify_expiry(token) == -1


def test_verify_expiry_rejects_malformed():
    assert SERVICE.verify_expiry("not.a.jwt") == -1


def test_verify_steam_jwt_rejects_wrong_audience():
    token = _fake_jwt({"iss": "steam", "aud": "other", "exp": 9999999999})
    assert SERVICE.verify_expiry(token) == -1


def test_jwt_expiry_label_no_token_vs_expired():
    from warestore.domain.auth.formatters import JWT_NO_TOKEN, format_jwt_expiry_label

    assert format_jwt_expiry_label(JWT_NO_TOKEN) == "No token"
    assert format_jwt_expiry_label(-1) == "JWT expired"
    assert format_jwt_expiry_label(120) == "JWT 2m"


def test_jwt_expiry_for_distinguishes_missing_token():
    from warestore.application.account_manager.features.accounts.presenter import (
        AccountsPresenter,
    )
    from warestore.domain.auth.formatters import JWT_NO_TOKEN

    class _Ctrl:
        def saved_token_entry(self, sid):
            return {"token": "x"} if sid == "has" else {}

        def verify_token_expiry(self, token):
            return -1  # present but expired

    p = AccountsPresenter(_Ctrl())
    assert p.jwt_expiry_for("has") == -1              # expired token -> "JWT expired"
    assert p.jwt_expiry_for("none") == JWT_NO_TOKEN   # no token -> "No token"
