"""Injector is not bundled — it's discovered in / downloaded to a persistent
per-user dir on demand."""

import pytest

from warestore.infrastructure.steam import injector_stage


def test_injector_path_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(injector_stage, "data_dir", lambda: str(tmp_path))
    assert injector_stage.injector_path() == str(tmp_path / "injector.exe")


def test_is_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(injector_stage, "data_dir", lambda: str(tmp_path))
    assert injector_stage.is_installed() is False
    (tmp_path / "injector.exe").write_bytes(b"X")
    assert injector_stage.is_installed() is True


def test_download_injector(monkeypatch, tmp_path):
    dest_dir = tmp_path / "bin"
    monkeypatch.setattr(injector_stage, "data_dir", lambda: str(dest_dir))

    def fake_retrieve(url, filename):
        with open(filename, "wb") as f:
            f.write(b"INJECTOR")

    monkeypatch.setattr(injector_stage.urllib.request, "urlretrieve", fake_retrieve)
    injector_stage.download_injector()
    assert injector_stage.is_installed()
    assert (dest_dir / "injector.exe").read_bytes() == b"INJECTOR"


def test_download_failure_cleans_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(injector_stage, "data_dir", lambda: str(tmp_path))

    def boom(url, filename):
        with open(filename, "wb") as f:
            f.write(b"partial")
        raise OSError("network down")

    monkeypatch.setattr(injector_stage.urllib.request, "urlretrieve", boom)
    with pytest.raises(OSError):
        injector_stage.download_injector()
    assert not injector_stage.is_installed()
    assert not (tmp_path / "injector.exe.part").exists()
