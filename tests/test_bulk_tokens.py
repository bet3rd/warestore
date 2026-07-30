from warestore.application.account_manager.controller import AccountManagerController

JWT_OK = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"
JWT_BAD = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIyIn0.sig"


def test_classify_bulk_tokens_skips_expired(monkeypatch):
    ctrl = AccountManagerController()
    text = f"alice----{JWT_OK}\nbob----{JWT_BAD}\n"

    def fake_verify(token: str) -> int:
        return 3600 if token == JWT_OK else -1

    monkeypatch.setattr(ctrl, "verify_token_expiry", fake_verify)

    importable, expired = ctrl.classify_bulk_tokens(text)
    assert importable == [f"alice----{JWT_OK}"]
    assert expired == [f"bob----{JWT_BAD}"]


def test_is_entry_importable(monkeypatch):
    ctrl = AccountManagerController()

    monkeypatch.setattr(ctrl, "verify_token_expiry", lambda token: 3600)

    assert ctrl.is_entry_importable(f"alice----{JWT_OK}") is True

    monkeypatch.setattr(ctrl, "verify_token_expiry", lambda token: -1)

    assert ctrl.is_entry_importable(f"alice----{JWT_OK}") is False
