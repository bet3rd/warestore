# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""One running Account Manager per user session.

Two cooperating mechanisms:

* ``acquire_single_instance_lock`` — an atomic ``QSharedMemory`` gate taken at
  the very top of ``main()``, before any UI (including the vault dialog). This
  is the authoritative "may I run?" check. Because it is atomic there is no
  time-of-check/time-of-use gap: two launches fired in quick succession cannot
  both win. On Windows the shared segment is kernel ref-counted, so it is
  released automatically when the owning process exits — even on a crash — so
  there are no stale locks to clear.
* ``QLocalServer`` / ``activate_existing_instance`` — best-effort IPC used only
  to raise the already-running window to the foreground. It binds late (inside
  the main window), so it must not be relied on as the gate.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QSharedMemory, pyqtSlot
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

_SOCKET_KEY = "warestore-account-manager"
_LOCK_KEY = "warestore-account-manager-lock"

# Held for the whole process lifetime so the segment stays mapped; Qt detaches
# (and the OS frees it) when the interpreter tears down at exit.
_lock: QSharedMemory | None = None


def acquire_single_instance_lock() -> bool:
    """Try to claim the single-instance lock. True if we may run.

    Returns False when another instance already holds it. On any unexpected
    error we fail open (return True) rather than lock the user out of their
    own app — the QLocalServer path still guards the common case.
    """
    global _lock
    shm = QSharedMemory(_LOCK_KEY)
    if shm.create(1):
        _lock = shm  # keep a reference alive for the process lifetime
        return True
    if shm.error() == QSharedMemory.AlreadyExists:
        return False
    _lock = shm
    return True


def activate_existing_instance(timeout_ms: int = 400) -> bool:
    """If another instance is listening, ask it to show and return True."""
    client = QLocalSocket()
    client.connectToServer(_SOCKET_KEY)
    if not client.waitForConnected(timeout_ms):
        return False
    client.write(b"show\n")
    client.flush()
    client.waitForBytesWritten(timeout_ms)
    client.disconnectFromServer()
    return True


class InstanceServer(QObject):
    def __init__(self, window) -> None:
        super().__init__()
        self._window = window
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        QLocalServer.removeServer(_SOCKET_KEY)
        if not self._server.listen(_SOCKET_KEY):
            raise RuntimeError(f"Could not bind single-instance socket: {_SOCKET_KEY}")

    @pyqtSlot()
    def _on_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(200)
        conn.readAll()
        conn.disconnectFromServer()
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
