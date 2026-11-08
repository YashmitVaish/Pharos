"""Curated Ubuntu notes, attached when the model reads a matching file.

The model is a general LLM and can be wrong about version-specific Ubuntu
behaviour. These short notes (with sources in HTML comments) fix the common cases.
"""
from __future__ import annotations

import re
from pathlib import Path

NOTES_DIR = Path(__file__).parent / "notes"
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

_SHELL_FILES = {"bashrc", "profile", "bash_profile", "bash_aliases", "zshrc", "zprofile"}


def note_name(path: Path) -> str | None:
    """Which note applies to this file? Matches by name and parent folders."""
    name = path.name
    parents = {p.name for p in path.parents}
    if name == "sshd_config" or "sshd_config.d" in parents:
        return "ssh"
    if "netplan" in parents and name.endswith((".yaml", ".yml")):
        return "netplan"
    if name in {"sources.list", "ubuntu.sources"} or {"sources.list.d", "apt.conf.d"} & parents:
        return "apt"
    if name == "fstab":
        return "fstab"
    if "ufw" in parents or name in {"ufw", "ufw.conf"}:
        return "ufw"
    if name == "sysctl.conf" or "sysctl.d" in parents:
        return "sysctl"
    if name.lstrip(".") in _SHELL_FILES:
        return "shell"
    return None


def notes_for(path: Path) -> str:
    key = note_name(path)
    if not key:
        return ""
    try:
        text = (NOTES_DIR / f"{key}.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    return _COMMENT_RE.sub("", text).strip()
