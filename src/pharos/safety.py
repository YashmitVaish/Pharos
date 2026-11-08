"""Safety layer: path allowlist, secret redaction and size caps.

Everything the model can see or touch passes through this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_READ_BYTES = 64 * 1024


class SafetyError(Exception):
    """Raised when a request is blocked by policy."""

_DENY_NAME_RE = [
    re.compile(p)
    for p in (
        r"^id_",
        r"^ssh_host_.*_key$",
        r"\.(pem|key|p12|pfx|kdbx|gpg|asc|keystore)$",
        r"^\.env($|\.)",
        r"^\.(netrc|pgpass|npmrc|pypirc|git-credentials)$",
        r"^g?shadow-?$",
        r"^sudoers",
        r"^credentials$",
    )
]

_DENY_DIRS = {
    ".gnupg", ".aws", ".kube", ".docker", ".password-store",
    "google-chrome", "chromium", "BraveSoftware", "gcloud", "rclone",
}


def deny_reason(path: Path) -> str | None:
    """Return why a (resolved) path is never allowed, or None."""
    parts = path.parts
    for part in parts:
        if part in _DENY_DIRS:
            return f"'{part}' holds credentials"
    if ".ssh" in parts and path.name != "config":
        return "files in .ssh other than 'config' can hold private keys"
    for rx in _DENY_NAME_RE:
        if rx.search(path.name):
            return f"'{path.name}' looks like a secret file"
    return None


@dataclass(frozen=True)
class Policy:
    """Which paths Pharos may read or edit."""

    base: Path  # relative paths are resolved against this
    roots: tuple[Path, ...] = ()  # directories, recursive
    files: tuple[Path, ...] = ()  # exact files
    home: Path | None = None  # dotfiles directly inside this dir are allowed

    def _expand(self, raw: str | Path) -> Path:
        s = str(raw)
        if s == "~" or s.startswith("~/"):
            home = self.home or Path.home()
            return home if s == "~" else home / s[2:]
        p = Path(s)
        return p if p.is_absolute() else self.base / p

    def allows(self, real: Path) -> bool:
        if real in self.files:
            return True
        for r in self.roots:
            if real == r or r in real.parents:
                return True
        return (
            self.home
            and real.parent == self.home
            and real.name.startswith(".")
            and not real.is_dir() or False
        )


    def resolve(self, raw: str | Path, listing: bool = False) -> Path:
        """Resolve symlinks and '..', then check deny rules and the allowlist."""
        real = self._expand(raw).resolve()
        reason = deny_reason(real)
        if reason:
            raise SafetyError(f"Blocked: {reason}.")
        if listing and self.home and real == self.home:
            return real
        if not self.allows(real):
            raise SafetyError(f"Blocked: {real} is outside the allowed locations.")
        return real

    def visible(self, p: Path) -> bool:
        """True if a directory entry may be shown or searched."""
        try:
            real = p.resolve()
        except OSError:
            return False
        return deny_reason(real) is None and self.allows(real)

    def home_dotfiles(self) -> list[Path]:
        if not self.home:
            return []
        try:
            return [
                p for p in sorted(self.home.iterdir())
                if p.name.startswith(".") and p.is_file() and self.visible(p)
            ]
        except OSError:
            return []


def default_policy(home: Path | None = None) -> Policy:
    home = (home or Path.home()).resolve()
    dirs = [
        home / ".config",
        Path("/etc/ssh"), Path("/etc/apt"), Path("/etc/systemd"),
        Path("/etc/netplan"), Path("/etc/default"), Path("/etc/sysctl.d"),
        Path("/etc/ufw"),
    ]
    files = [
        home / ".ssh" / "config",
        Path("/etc/fstab"), Path("/etc/hosts"), Path("/etc/hostname"),
        Path("/etc/environment"), Path("/etc/sysctl.conf"),
        Path("/etc/resolv.conf"), Path("/etc/crontab"),
    ]
    return Policy(
        base=home,
        roots=tuple(d.resolve() for d in dirs),
        files=tuple(f.resolve() for f in files),
        home=home,
    )


def sandbox_policy(root: Path) -> Policy:
    """Only this folder is reachable (used by `pharos demo` and --root)."""
    root = root.resolve()
    return Policy(base=root, roots=(root,))


_SECRET_WORDS = (
    r"(?:pass(?:word|wd|phrase)?|pwd|secret|token|api[_-]?key|access[_-]?key"
    r"|private[_-]?key|psk|credential)"
)

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    (re.compile(r"(://[^/\s:@]+:)[^@/\s]+@"), r"\1[REDACTED]@"),
    (
        re.compile(
            r"^(?P<lead>[ \t]*(?:export[ \t]+)?[\w.\-\"']*" + _SECRET_WORDS
            + r"[\w.\-\"']*[ \t]*[:=][ \t]*)(?P<val>\S.*)$",
            re.IGNORECASE | re.MULTILINE,
        ),
        r"\g<lead>[REDACTED]",
    ),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), "[REDACTED]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
        "[REDACTED]",
    ),
    (re.compile(r"(?i)(bearer[ \t]+)[A-Za-z0-9._\-]{16,}"), r"\1[REDACTED]"),
]


def redact(text: str) -> tuple[str, int]:
    """Replace likely secrets with [REDACTED]. Returns (text, number of hits)."""
    total = 0
    for rx, repl in _PATTERNS:
        text, n = rx.subn(repl, text)
        total += n
    return text, total
