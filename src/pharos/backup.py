"""Backups and undo. Every write is preceded by a timestamped backup."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class BackupError(Exception):
    pass


def pharos_home() -> Path:
    return Path(os.environ.get("PHAROS_HOME") or Path.home() / ".pharos")


def _history_file() -> Path:
    return pharos_home() / "history.json"


def _load() -> list[dict]:
    try:
        return json.loads(_history_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(history: list[dict]) -> None:
    f = _history_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, indent=2), encoding="utf-8")
    os.replace(tmp, f)


def backup_file(path: Path) -> Path:
    d = pharos_home() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = hashlib.sha1(str(path).encode()).hexdigest()[:8]
    dest = d / f"{stamp}_{tag}_{path.name}"
    i = 1
    while dest.exists():
        dest = d / f"{stamp}_{tag}_{i}_{path.name}"
        i += 1
    shutil.copy2(path, dest)
    return dest


def _replace_atomically(dst: Path, write) -> None:
    """Write a temp file next to dst, copy the mode over, then rename onto dst."""
    mode = dst.stat().st_mode & 0o7777
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=".pharos-")
    os.close(fd)
    try:
        write(Path(tmp))
        os.chmod(tmp, mode)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@dataclass
class ApplyResult:
    applied: bool
    backup: Path
    command: str | None = None  # run this yourself if Pharos lacked permission


def apply_edit(path: Path, new_text: str) -> ApplyResult:
    """Back up `path`, then replace its contents. Never uses sudo."""
    path = Path(path)
    bak = backup_file(path)
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "path": str(path),
        "backup": str(bak),
        "undone": False,
    }
    try:
        _replace_atomically(
            path,
            lambda tmp: tmp.write_bytes(new_text.encode("utf-8")),
        )
        result = ApplyResult(True, bak)
    except PermissionError:
        prop = pharos_home() / "proposed"
        prop.mkdir(parents=True, exist_ok=True)
        f = prop / f"{time.strftime('%Y%m%d-%H%M%S')}_{path.name}"
        f.write_bytes(new_text.encode("utf-8"))
        cmd = f"sudo cp {shlex.quote(str(f))} {shlex.quote(str(path))}"
        result = ApplyResult(False, bak, cmd)
    history = _load()
    history.append(entry)
    _save(history)
    return result


@dataclass
class UndoResult:
    restored: bool
    path: Path
    backup: Path
    command: str | None = None


def undo() -> UndoResult:
    """Restore the most recent change that has not been undone."""
    history = _load()
    for entry in reversed(history):
        if entry.get("undone"):
            continue
        path, bak = Path(entry["path"]), Path(entry["backup"])
        if not bak.exists():
            raise BackupError(f"Backup file is missing: {bak}")
        try:
            _replace_atomically(path, lambda tmp: shutil.copyfile(bak, tmp))
            result = UndoResult(True, path, bak)
        except PermissionError:
            cmd = f"sudo cp -p {shlex.quote(str(bak))} {shlex.quote(str(path))}"
            result = UndoResult(False, path, bak, cmd)
        entry["undone"] = True
        _save(history)
        return result
    raise BackupError("Nothing to undo.")
