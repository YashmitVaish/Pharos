"""The only things the model can do. Every tool goes through the safety layer."""
from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .notes import notes_for
from .safety import MAX_READ_BYTES, Policy, SafetyError, deny_reason, redact

NOTES_MARKER = "=== PHAROS NOTES (trusted Ubuntu reference, not part of the file) ==="
MAX_LIST = 200
MAX_HITS = 50
MAX_FILES_SCANNED = 5000
MAX_SEARCH_FILE_BYTES = 256 * 1024
MAX_CMD_OUTPUT = 8 * 1024
_UNIT_RE = re.compile(r"^[A-Za-z0-9@._\-]{1,100}$")
_MAN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+\-]{0,60}$")
_MAN_SECTION_RE = re.compile(r"^[1-8]$")
_PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]{0,80}$")
MAX_MAN_CHARS = 8 * 1024
MAX_MAN_MATCH_CHARS = 3 * 1024


class ToolError(Exception):
    """A tool call that cannot be carried out (bad input, missing file...)."""


@dataclass
class Proposal:
    path: Path
    old: str
    new: str
    reason: str
    diff: str


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_STR = {"type": "string"}

_READ_SCHEMAS = [
    _fn("list_dir", "List files in an allowed directory (default: home).",
        {"path": _STR}, []),
    _fn("read_file", "Read an allowed text file (secrets are shown as [REDACTED]).",
        {"path": _STR}, ["path"]),
    _fn("search_files", "Case-insensitive text search across allowed config files.",
        {"query": _STR, "path": {"type": "string", "description": "optional file or directory"}},
        ["query"]),
    _fn("service_status", "Show `systemctl status` for one service, e.g. ssh or NetworkManager.",
        {"unit": _STR}, ["unit"]),
    _fn("journal_tail", "Show the last lines of a service's journal (max 100).",
        {"unit": _STR, "lines": {"type": "integer"}}, ["unit"]),
    _fn("man_page",
        "Read the installed man page for a command or config file, e.g. name=sshd_config "
        "section=5 query=PermitRootLogin. Use query to get only the matching paragraphs. "
        "This is the authoritative reference for this machine's version.",
        {"name": _STR, "section": {"type": "string", "description": "1-8, optional"},
         "query": {"type": "string", "description": "keyword to look for, optional"}},
        ["name"]),
    _fn("package_version", "Show the installed version of a Debian/Ubuntu package.",
        {"name": _STR}, ["name"]),
]

_EDIT_SCHEMA = _fn(
    "propose_edit",
    "Propose ONE exact text replacement in a file. Nothing is written until the user "
    "approves the diff. old_text must appear exactly once in the file.",
    {"path": _STR, "old_text": _STR, "new_text": _STR,
     "reason": {"type": "string", "description": "one plain-language sentence"}},
    ["path", "old_text", "new_text", "reason"],
)

READ_TOOLS = {
    "list_dir", "read_file", "search_files", "service_status", "journal_tail",
    "man_page", "package_version",
}


class ToolBox:
    def __init__(self, policy: Policy, allow_edit: bool = False):
        self.policy = policy
        self.allow_edit = allow_edit
        self.proposals: list[Proposal] = []
        self._pending: dict[Path, str] = {}

    # ------------------------------------------------------------- plumbing

    def schemas(self) -> list[dict]:
        return _READ_SCHEMAS + ([_EDIT_SCHEMA] if self.allow_edit else [])

    def call(self, name: str, args: dict) -> str:
        """Run a tool. Never raises: errors come back as text for the model."""
        allowed = READ_TOOLS | ({"propose_edit"} if self.allow_edit else set())
        if name not in allowed:
            return f"error: unknown tool '{name}'"
        if not isinstance(args, dict):
            return "error: arguments must be an object"
        try:
            return getattr(self, name)(**args)
        except (SafetyError, ToolError) as e:
            return f"error: {e}"
        except TypeError as e:
            return f"error: bad arguments ({e})"
        except OSError as e:
            return f"error: {e.strerror or e}"

    def final_texts(self) -> dict[Path, str]:
        """Final content per file after all proposals, in order."""
        return dict(self._pending)

    # ---------------------------------------------------------------- tools

    def list_dir(self, path: str = "~") -> str:
        real = self.policy.resolve(path, listing=True)
        if not real.is_dir():
            raise ToolError(f"{real} is not a directory")
        lines = []
        for e in sorted(real.iterdir(), key=lambda p: p.name):
            if not self.policy.visible(e):
                continue
            lines.append(e.name + ("/" if e.is_dir() else f"  ({e.stat().st_size} bytes)"))
            if len(lines) >= MAX_LIST:
                lines.append("... (list truncated)")
                break
        return f"# {real}\n" + ("\n".join(lines) if lines else "(nothing visible here)")

    def read_file(self, path: str) -> str:
        real = self.policy.resolve(path)
        if not real.is_file():
            raise ToolError(f"{real} is not a file")
        with real.open("rb") as f:
            raw = f.read(MAX_READ_BYTES + 1)
        truncated = len(raw) > MAX_READ_BYTES
        raw = raw[:MAX_READ_BYTES]
        if b"\x00" in raw[:1024]:
            raise ToolError("binary file, not shown")
        text, n = redact(raw.decode("utf-8", errors="replace"))
        header = f"# {real}" + (f"  ({n} secret value(s) redacted)" if n else "")
        if truncated:
            text += "\n# [truncated at 64 KB]"
        out = header + "\n" + text
        notes = notes_for(real)
        if notes:
            out += f"\n\n{NOTES_MARKER}\n{notes}"
        return out

    def _iter_files(self, path: str):
        scanned = 0
        if path:
            real = self.policy.resolve(path, listing=True)
            if real.is_file():
                yield real
                return
            if self.policy.home and real == self.policy.home:
                yield from self.policy.home_dotfiles()
                return
            starts = [real]
        else:
            yield from self.policy.home_dotfiles()
            yield from (f for f in self.policy.files if f.is_file())
            starts = [r for r in self.policy.roots if r.is_dir()]
        for start in starts:
            for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
                dirnames[:] = [d for d in dirnames if self.policy.visible(Path(dirpath, d))]
                for name in filenames:
                    f = Path(dirpath, name)
                    if self.policy.visible(f):
                        scanned += 1
                        if scanned > MAX_FILES_SCANNED:
                            return
                        yield f

    def search_files(self, query: str, path: str = "") -> str:
        q = query.strip().lower()
        if len(q) < 2:
            raise ToolError("query is too short")
        hits: list[str] = []
        for f in self._iter_files(path):
            try:
                if f.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    continue
                text = f.read_bytes().decode("utf-8", errors="replace")
            except OSError:
                continue
            if "\x00" in text[:1024]:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if q in line.lower():
                    clean, _ = redact(line.strip())
                    hits.append(f"{f}:{i}: {clean[:200]}")
                    if len(hits) >= MAX_HITS:
                        return "\n".join(hits) + "\n... (more matches not shown)"
        return "\n".join(hits) if hits else "no matches"

    def _exec(self, argv: list[str], extra_env: dict[str, str] | None = None) -> tuple[int, str]:
        """Run a fixed command (no shell). Returns (exit code, stdout + stderr)."""
        if not shutil.which(argv[0]):
            raise ToolError(f"{argv[0]} is not available on this system")
        env = {**os.environ, **(extra_env or {})}
        try:
            r = subprocess.run(
                argv, capture_output=True, text=True, timeout=10, check=False, env=env,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise ToolError("command timed out")
        return r.returncode, (r.stdout + r.stderr).strip()

    def _run(self, argv: list[str]) -> str:
        _, raw = self._exec(argv)
        out, _ = redact(raw)
        return out[:MAX_CMD_OUTPUT] or "(no output)"

    def service_status(self, unit: str) -> str:
        if not _UNIT_RE.match(unit):
            raise ToolError("invalid unit name")
        return self._run(["systemctl", "status", "--no-pager", "-n", "20", unit])

    def journal_tail(self, unit: str, lines: int = 50) -> str:
        if not _UNIT_RE.match(unit):
            raise ToolError("invalid unit name")
        n = max(1, min(int(lines), 100))
        return self._run(["journalctl", "-u", unit, "-n", str(n), "--no-pager"])

    @staticmethod
    def _clean_man(text: str) -> str:
        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)  # ANSI colours
        return re.sub(r".\x08", "", text)  # nroff bold/underline overstrikes

    @staticmethod
    def _man_matches(text: str, query: str) -> str:
        q = query.strip().lower()
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if q in b.lower()]
        if not blocks:
            return f"no paragraph mentions '{query}' in this man page"
        out, used = [], 0
        for b in blocks:
            if used + len(b) > MAX_MAN_MATCH_CHARS and out:
                break
            out.append(b[:MAX_MAN_MATCH_CHARS])
            used += len(b)
        return "\n\n".join(out)

    def man_page(self, name: str, section: str = "", query: str = "") -> str:
        if not _MAN_NAME_RE.match(name):
            raise ToolError("invalid man page name")
        if section and not _MAN_SECTION_RE.match(str(section)):
            raise ToolError("section must be a single digit 1-8")
        argv = ["man", "-P", "cat"] + ([str(section)] if section else []) + [name]
        code, raw = self._exec(argv, {"MANWIDTH": "100", "LC_ALL": "C.UTF-8"})
        if code != 0:
            return f"error: {raw[:300] or 'no manual entry'}"
        text = self._clean_man(raw)
        body = self._man_matches(text, query) if query.strip() else text[:MAX_MAN_CHARS]
        return f"# man {section + ' ' if section else ''}{name}\n{body}"

    def package_version(self, name: str) -> str:
        if not _PKG_RE.match(name):
            raise ToolError("invalid package name")
        code, raw = self._exec(
            ["dpkg-query", "-W", "-f=${Package} ${Version} (${db:Status-Abbrev})\n", name]
        )
        return raw[:300] if code == 0 else f"{name}: not installed or unknown package"

    def propose_edit(self, path: str, old_text: str, new_text: str, reason: str) -> str:
        real = self.policy.resolve(path)
        if not real.is_file():
            raise ToolError(f"{real} is not a file")
        if "[REDACTED" in old_text or "[REDACTED" in new_text:
            raise ToolError(
                "never include [REDACTED] in an edit; leave lines with secrets untouched"
            )
        if not old_text:
            raise ToolError("old_text must not be empty")
        if real in self._pending:
            current = self._pending[real]
        else:
            if real.stat().st_size > MAX_READ_BYTES:
                raise ToolError("file is too large to edit safely")
            try:
                current = real.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                raise ToolError("file is not valid UTF-8; refusing to edit")
        count = current.count(old_text)
        if count != 1:
            raise ToolError(
                f"old_text must match exactly once, but matched {count} times; "
                "copy it exactly from read_file output"
            )
        updated = current.replace(old_text, new_text, 1)
        diff = "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"{real} (current)",
                tofile=f"{real} (proposed)",
            )
        )
        self._pending[real] = updated
        self.proposals.append(Proposal(real, old_text, new_text, reason, diff))
        return "Proposal recorded. The user will review the diff before anything changes."
