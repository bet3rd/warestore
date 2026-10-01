import base64
import json
import time

import pytest

from warestore.infrastructure.steam import cs2_gc_proto as gp
from warestore.infrastructure.steam.cs2_cm_mint import TokenRejectedError
from warestore.infrastructure.steam import cs2_session
from warestore.infrastructure.steam.cs2_session import (
    AccountInUseError,
    Cs2Session,
    GcUnavailableError,
    account_in_use,
)

SID = 76561198000000001
ACCT = SID & 0xFFFFFFFF


def _token():
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64({'sub': str(SID)})}.sig"


class FakeClient:
    def __init__(self):
        self.games = []
        self.disconnected = False
        self.handlers = {}

    def on(self, emsg, fn):
        self.handlers.setdefault(emsg, []).append(fn)

    def games_played(self, apps):
        self.games.append(list(apps))
        for fn in self.handlers.get(gp.MSG_CLIENT_PLAYING_SESSION_STATE, []):
            self._maybe_fire(fn)

    def _maybe_fire(self, fn):
        pass  # overridden by PlayingElsewhereClient

    def disconnect(self):
        self.disconnected = True

    def sleep(self, _s):
        pass


class PlayingElsewhereClient(FakeClient):
    """Fires ClientPlayingSessionState(blocked=1, app=730) right after games_played."""

    def _maybe_fire(self, fn):
        payload = (
            gp.encode_varint((2 << 3) | 0) + gp.encode_varint(1)
            + gp.encode_varint((3 << 3) | 0) + gp.encode_varint(730)
        )
        fn(type("Msg", (), {"payload": payload})())


class FakeGC:
    """Scripted GC: answers hello with `welcome`; an equip rewrites it."""

    def __init__(self, welcome=b"", *, answers_hello=True, apply_equips=True, profile=None, mm=None):
        self.welcome = welcome
        self.answers_hello = answers_hello
        self.apply_equips = apply_equips
        self.profile = profile
        self.mm = mm
        self.sent = []
        self.handlers = {}
        self.pending = {}

    def on(self, emsg, fn):
        self.handlers.setdefault(emsg, []).append(fn)

    def send(self, header, body):
        self.sent.append((header.msg, body))
        if header.msg == gp.MSG_CLIENT_HELLO and self.answers_hello:
            self.pending[gp.MSG_CLIENT_WELCOME] = self.welcome
        elif header.msg == gp.MSG_ADJUST_EQUIP_SLOTS:
            if self.apply_equips:
                objs = []
                for _n, _w, slot in gp.iter_fields(body):
                    if isinstance(slot, bytes):
                        f = {n: v for n, _w2, v in gp.iter_fields(slot)}
                        objs.append((3, gp.encode_equip_slot_object(ACCT, f[1], f[2], f[3] & 0xFFFF)))
                self.welcome = gp.encode_welcome(objs)
            for fn in self.handlers.get(gp.MSG_ADJUST_EQUIP_SLOTS, []):
                fn(None, b"")
        elif header.msg == gp.MSG_PROFILE_REQUEST and self.profile is not None:
            self.pending[gp.MSG_PROFILE] = self.profile
        elif header.msg == gp.MSG_MM_HELLO and self.mm is not None:
            self.pending[gp.MSG_MM_HELLO_REPLY] = self.mm

    def wait_event(self, emsg, timeout=None):
        if emsg in self.pending:
            return (None, self.pending.pop(emsg))
        return None


def _session(gc, *, in_use_reason=None, read_only=False, client=None, deadline=None):
    client = client or FakeClient()
    s = Cs2Session(
        _token(),
        read_only=read_only,
        logon=lambda tok, deadline=None: (client, SID, tok),
        gc_factory=lambda c: gc,
        in_use_probe=lambda sid: in_use_reason,
        deadline=deadline,
    )
    s.HELLO_TIMEOUT = 0.01  # tests never wait
    return s, client


def test_in_use_probe_reason_refuses_with_that_message():
    s, _ = _session(FakeGC(), in_use_reason="playing a game on this PC")
    with pytest.raises(AccountInUseError, match="playing a game on this PC"):
        s.__enter__()


def test_logged_in_but_idle_target_is_allowed():
    welcome = gp.encode_welcome([(3, gp.encode_equip_slot_object(ACCT, gp.TEAM_T, 4, 64))])
    s, _ = _session(FakeGC(welcome), in_use_reason=None)
    with s:
        assert s.read_loadout()[(gp.TEAM_T, 4)] == 64


def test_read_only_no_longer_changes_the_in_use_rule():
    s, _ = _session(FakeGC(), in_use_reason="playing a game on this PC", read_only=True)
    with pytest.raises(AccountInUseError):
        s.__enter__()


def test_playing_on_another_device_is_detected_during_hello_without_waiting_full_budget():
    client = PlayingElsewhereClient()
    s, _ = _session(FakeGC(answers_hello=False), client=client)
    s.HELLO_TIMEOUT = 10.0  # would normally retry for a while; must bail out fast
    s.HELLO_RETRY = 10.0
    start = time.monotonic()
    with pytest.raises(AccountInUseError, match="playing on another device"):
        s.__enter__()
    assert time.monotonic() - start < 5.0


def test_gc_silence_raises_and_still_cleans_up():
    client = FakeClient()
    s, _ = _session(FakeGC(answers_hello=False), client=client)
    with pytest.raises(GcUnavailableError):
        with s:
            pass
    assert client.games[-1] == [] and client.disconnected


def test_write_loadout_sends_only_differences_and_reads_back():
    gc = FakeGC(gp.encode_welcome([]))
    s, _ = _session(gc)
    want = gp.resolve_loadout({(gp.TEAM_T, 4): 64, (gp.TEAM_CT, 17): 38})
    with s:
        matched, total, changed = s.write_loadout(want)
    assert (matched, total, changed) == (30, 30, 2)
    equip = [body for msg, body in gc.sent if msg == gp.MSG_ADJUST_EQUIP_SLOTS]
    assert len(equip) == 1
    slots = [f for f in gp.iter_fields(equip[0]) if f[0] == 1]
    assert len(slots) == 2


def test_write_loadout_reports_slots_the_gc_ignored():
    gc = FakeGC(gp.encode_welcome([]), apply_equips=False)
    s, _ = _session(gc)
    want = gp.resolve_loadout({(gp.TEAM_T, 4): 64})
    with s:
        assert s.write_loadout(want) == (29, 30, 1)


def test_profile_and_cooldown():
    me = gp.encode_account_profile(ACCT, level=6, premier_rating=15_000, premier_wins=30)
    mm = gp.encode_account_profile(ACCT, cooldown_seconds=600)
    gc = FakeGC(gp.encode_welcome([]), profile=gp.encode_players_profile([me]), mm=mm)
    s, _ = _session(gc)
    with s:
        prof = s.profile()
        assert (prof.level, prof.premier_rating) == (6, 15_000)
        assert s.cooldown_seconds() == 600


def test_past_deadline_raises_gc_unavailable_quickly():
    """I1: a session whose deadline has already passed must fail fast instead
    of running the (several seconds long) hello retry loop."""
    s, client = _session(FakeGC(answers_hello=True), deadline=time.monotonic() - 1)
    with pytest.raises(GcUnavailableError):
        s.__enter__()
    assert client.disconnected


def test_rejected_token_propagates():
    def logon(_tok, deadline=None):
        raise TokenRejectedError("InvalidPassword")
    s = Cs2Session(_token(), logon=logon, gc_factory=lambda c: FakeGC(), in_use_probe=lambda sid: None)
    with pytest.raises(TokenRejectedError):
        s.__enter__()


# --- account_in_use ----------------------------------------------------------

def _patch_probe(monkeypatch, *, active=0, running_app=0, names=frozenset()):
    monkeypatch.setattr(cs2_session, "_steam_registry", lambda: (active, running_app))
    monkeypatch.setattr(cs2_session, "_process_names", lambda: set(names))


def test_account_in_use_idle_is_none(monkeypatch):
    _patch_probe(monkeypatch, active=ACCT, running_app=0, names={"steam.exe"})
    assert account_in_use(SID) is None


def test_account_in_use_running_app_id_is_a_reason(monkeypatch):
    _patch_probe(monkeypatch, active=ACCT, running_app=730, names={"steam.exe"})
    assert account_in_use(SID) == "playing a game on this PC"


def test_account_in_use_cs2_process_is_a_reason(monkeypatch):
    _patch_probe(monkeypatch, active=ACCT, running_app=0, names={"steam.exe", "cs2.exe"})
    assert account_in_use(SID) == "playing a game on this PC"


def test_account_in_use_different_active_user_is_none(monkeypatch):
    _patch_probe(monkeypatch, active=ACCT + 1, running_app=730, names={"steam.exe", "cs2.exe"})
    assert account_in_use(SID) is None
