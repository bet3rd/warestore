import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QSharedMemory
from PyQt5.QtWidgets import QApplication

from warestore.presentation.account_manager.support import single_instance
from warestore.presentation.account_manager.support.single_instance import (
    acquire_single_instance_lock,
)


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _reset_lock(_app):
    # A real running WareStore holds this exact lock, which would make every
    # assertion here fail for the right reason — skip rather than force the
    # developer to close the app to run the suite.
    probe = QSharedMemory(single_instance._LOCK_KEY)
    if not probe.create(1) and probe.error() == QSharedMemory.AlreadyExists:
        pytest.skip("a WareStore instance is running and holds the single-instance lock")
    probe.detach()

    # Each test starts with no lock held and cleans up after itself, so the
    # module-level segment from one test can't leak into the next.
    single_instance._lock = None
    yield
    single_instance._lock = None


def test_first_acquire_succeeds(_app):
    assert acquire_single_instance_lock() is True


def test_second_acquire_is_blocked(_app):
    assert acquire_single_instance_lock() is True
    # A second, independent segment on the same key sees it already exists —
    # this is what a second process launch observes.
    other = QSharedMemory(single_instance._LOCK_KEY)
    assert other.create(1) is False
    assert other.error() == QSharedMemory.AlreadyExists


def test_lock_released_when_reference_dropped(_app):
    assert acquire_single_instance_lock() is True
    # Dropping the only reference detaches the segment; on Windows the kernel
    # then frees it, so a fresh acquire can claim the key again.
    single_instance._lock = None
    assert acquire_single_instance_lock() is True
