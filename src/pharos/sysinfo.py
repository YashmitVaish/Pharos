"""Describe the machine Pharos runs on, so advice is for *this* system."""
from __future__ import annotations

import os
import platform
from pathlib import Path


def parse_os_release(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key] = value.strip().strip('"').strip("'")
    return out


def read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    try:
        return parse_os_release(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def describe(os_release: dict[str, str] | None = None) -> str:
    """One line for the system prompt. Contains no hostname, user or IP."""
    info = read_os_release() if os_release is None else os_release
    name = info.get("PRETTY_NAME") or "an unknown Linux distribution"
    if info.get("VERSION_CODENAME"):
        name += f" (codename {info['VERSION_CODENAME']})"
    parts = [name, f"kernel {platform.release()}", platform.machine()]
    parts.append("init: systemd" if Path("/run/systemd/system").is_dir() else "init: not systemd")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP")
    if desktop:
        parts.append(f"desktop: {desktop}")
    line = "This machine: " + ", ".join(parts) + "."
    ids = {info.get("ID", ""), *info.get("ID_LIKE", "").split()}
    if "ubuntu" not in ids:
        line += (
            " This is not Ubuntu. Pharos is built for Ubuntu, so say clearly when "
            "advice may differ on this system."
        )
    return line
