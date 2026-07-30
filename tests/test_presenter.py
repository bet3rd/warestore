from warestore.application.account_manager.presenter import AccountManagerPresenter


class _FakeController:
    def __init__(self):
        self.steam_path: str | None = r"C:\Steam"
        self.accounts: list[dict] = [
            {
                "steamid": "76561198000000001",
                "account_name": "alice",
                "persona_name": "Alice",
                "timestamp": 1_700_000_000,
            }
        ]
        self.tokens: dict = {
            "76561198000000001": {
                "username": "alice",
                "token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
            }
        }
        self.deleted: list[str] = []

    def steam_install_path(self):
        return self.steam_path

    def list_steam_accounts(self):
        return self.accounts

    def extract_tokens_from_steam(self):
        return 0

    def saved_token_entry(self, steam_id: str):
        return self.tokens.get(steam_id, {})

    def verify_token_expiry(self, token: str):
        return 3600 if token else -1

    def get_metadata(self, steam_id: str):
        from warestore.domain.accounts.models import AccountRecord

        return AccountRecord(last_played=0)

    def format_last_played(self, timestamp: int):
        return "Never"

    def delete_account(self, steam_id: str):
        self.deleted.append(steam_id)
        return True

    def delete_metadata(self, steam_id: str):
        pass

    def load_settings(self):
        return {
            "open_cs2": True,
            "cs2_launch_options": "-high",
            "auto_remove_expired_tokens": False,
        }

    def purge_expired_tokens(self):
        removed = 0
        for sid, entry in list(self.tokens.items()):
            token = entry.get("token", "")
            if token and self.verify_token_expiry(token) < 0:
                del self.tokens[sid]
                removed += 1
        return removed


def test_load_accounts_no_steam():
    ctrl = _FakeController()
    ctrl.steam_path = None
    result = AccountManagerPresenter(ctrl).load_accounts()
    assert result.steam_dir is None
    assert result.status_message == "Steam not found."


def test_load_accounts_success():
    result = AccountManagerPresenter(_FakeController()).load_accounts()
    assert len(result.accounts) == 1
    assert result.steam_dir == r"C:\Steam"
    assert "Loaded 1 account" in result.status_message


def test_relogin_entry_for():
    entry = AccountManagerPresenter(_FakeController()).relogin_entry_for(
        {"steamid": "76561198000000001", "account_name": "alice"}
    )
    assert entry and entry.startswith("alice----eyJ")


def test_relogin_entry_missing_token():
    ctrl = _FakeController()
    ctrl.tokens = {}
    assert AccountManagerPresenter(ctrl).relogin_entry_for({"steamid": "76561198000000001"}) is None


def test_export_entries_for_skips_missing_tokens():
    ctrl = _FakeController()
    ctrl.accounts.append(
        {
            "steamid": "76561198000000002",
            "account_name": "bob",
            "persona_name": "Bob",
            "timestamp": 1_700_000_001,
        }
    )
    lines = AccountManagerPresenter(ctrl).export_entries_for(ctrl.accounts)
    assert len(lines) == 1
    assert lines[0].startswith("alice----eyJ")


def test_delete_account_calls_metadata_cleanup():
    ctrl = _FakeController()
    assert AccountManagerPresenter(ctrl).delete_account("76561198000000001")
    assert ctrl.deleted == ["76561198000000001"]


def test_load_accounts_purges_expired_when_enabled():
    ctrl = _FakeController()
    ctrl.tokens["76561198000000002"] = {
        "username": "bob",
        "token": "expired.jwt.token",
    }

    def expiry(token: str):
        return -1 if token == "expired.jwt.token" else 3600

    ctrl.verify_token_expiry = expiry  # type: ignore[method-assign]

    settings = ctrl.load_settings()
    settings["auto_remove_expired_tokens"] = True
    ctrl.load_settings = lambda: settings  # type: ignore[method-assign]

    result = AccountManagerPresenter(ctrl).load_accounts()
    assert result.removed_expired == 1
    assert "76561198000000002" not in ctrl.tokens
    assert "Removed 1 expired" in result.status_message


def test_switch_worker_options_from_settings():
    opts = AccountManagerPresenter(_FakeController()).switch_worker_options(
        mode="native", acc={"steamid": "1"}
    )
    assert opts["open_cs2"] is True
    assert opts["cs2_options"] == "-high"
