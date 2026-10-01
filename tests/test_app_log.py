import threading

from warestore.presentation.account_manager.support.app_log import AppLog


def test_version_moves_on_append_and_clear_only():
    log = AppLog()
    v0 = log.version
    log.append("a")
    assert log.version == v0 + 1
    log.append("\n")  # blank lines are dropped and don't count as a change
    assert log.version == v0 + 1
    log.clear()
    assert log.version == v0 + 2 and log.lines() == []


def test_reading_while_another_thread_appends_never_raises():
    log = AppLog(max_lines=50)
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            log.append("x")

    t = threading.Thread(target=writer)
    t.start()
    try:
        for _ in range(2000):
            log.lines()  # a bare list(deque) can raise "deque mutated during iteration"
    finally:
        stop.set()
        t.join()
