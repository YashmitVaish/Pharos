import os
import stat

import pytest

from pharos.backup import BackupError, apply_edit, undo


@pytest.fixture(autouse=True)
def pharos_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PHAROS_HOME", str(tmp_path / "pharos_home"))


def test_apply_then_undo_restores_exact_bytes_and_mode(tmp_path):
    f = tmp_path / "conf"
    original = b"line1\r\nline2\n"
    f.write_bytes(original)
    os.chmod(f, 0o640)

    res = apply_edit(f, "changed\n")
    assert res.applied and res.backup.exists()
    assert f.read_text() == "changed\n"
    assert stat.S_IMODE(f.stat().st_mode) == 0o640

    out = undo()
    assert out.restored
    assert f.read_bytes() == original
    assert stat.S_IMODE(f.stat().st_mode) == 0o640


def test_undo_walks_back_through_history(tmp_path):
    f = tmp_path / "conf"
    f.write_text("v1")
    apply_edit(f, "v2")
    apply_edit(f, "v3")
    undo()
    assert f.read_text() == "v2"
    undo()
    assert f.read_text() == "v1"
    with pytest.raises(BackupError):
        undo()


def test_undo_with_no_history_errors():
    with pytest.raises(BackupError):
        undo()


def test_no_stray_temp_files_left(tmp_path):
    f = tmp_path / "conf"
    f.write_text("a")
    apply_edit(f, "b")
    assert [p.name for p in tmp_path.iterdir() if p.name != "pharos_home"] == ["conf"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_no_permission_returns_sudo_command_and_never_runs_it(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    f = d / "conf"
    f.write_text("orig")
    os.chmod(d, 0o555)
    try:
        res = apply_edit(f, "new")
    finally:
        os.chmod(d, 0o755)
    assert not res.applied
    assert res.command and res.command.startswith("sudo cp ")
    assert f.read_text() == "orig"
