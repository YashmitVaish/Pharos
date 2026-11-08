"""Command-line interface."""
from __future__ import annotations

import argparse
import difflib
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax

from . import __version__
from .backup import BackupError, apply_edit, pharos_home, undo
from .model import BharatCodeBackend, ModelError, run_agent
from .prompts import ASK, EXPLAIN, PROPOSE, WHERE, WHY, system_prompt
from .safety import Policy, SafetyError, default_policy, sandbox_policy
from .tools import ToolBox

console = Console()

COMMANDS = ("explain", "why", "where", "propose", "ask", "undo", "demo")
_VALUE_FLAGS = {"--root", "--model"}


def _show_tool(name: str, args: dict) -> None:
    detail = args.get("path") or args.get("unit") or args.get("name") or args.get("query") or ""
    console.print(f"[dim]→ {escape(name)} {escape(str(detail))}[/dim]")


def _confirm(question: str) -> bool:
    try:
        return console.input(f"[bold]{question}[/bold] [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


# ------------------------------------------------------------------ commands

def cmd_explain(policy: Policy, backend: BharatCodeBackend, path: str) -> int:
    content = ToolBox(policy).read_file(path)
    msg = backend.chat([
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": EXPLAIN.format(content=content)},
    ])
    console.print(Markdown(msg["content"]))
    return 0


def cmd_investigate(policy: Policy, backend: BharatCodeBackend, template: str, **kw: str) -> int:
    answer = run_agent(
        backend, ToolBox(policy), system_prompt(), template.format(**kw), on_tool=_show_tool
    )
    console.print(Markdown(answer))
    return 0


def _run_with_edits(policy: Policy, backend: BharatCodeBackend, prompt: str) -> int:
    """Run the agent with edit proposals enabled; show diffs; apply only after approval."""
    tb = ToolBox(policy, allow_edit=True)
    answer = run_agent(backend, tb, system_prompt(), prompt, on_tool=_show_tool)
    console.print(Markdown(answer))
    if not tb.proposals:
        return 0
    for p in tb.proposals:
        console.print(Panel(
            Syntax(p.diff, "diff", theme="ansi_dark"),
            title=escape(str(p.path)),
            subtitle=escape(p.reason),
        ))
    if not _confirm(f"Apply {len(tb.proposals)} change(s)? A backup is made first."):
        console.print("Nothing was changed.")
        return 0
    for path, text in tb.final_texts().items():
        res = apply_edit(path, text)
        if res.applied:
            console.print(f"[green]Updated[/green] {escape(str(path))}  (backup: {escape(str(res.backup))})")
        else:
            console.print(
                f"[yellow]No permission to write {escape(str(path))}.[/yellow] "
                f"Backup saved to {escape(str(res.backup))}. To apply the change yourself, run:\n\n"
                f"  {escape(res.command or '')}\n"
            )
    console.print("Undo with: [bold]pharos undo[/bold]")
    return 0


def cmd_propose(policy: Policy, backend: BharatCodeBackend, goal: str, file: str | None) -> int:
    prompt = PROPOSE.format(goal=goal) + (f"\nStart with this file: {file}" if file else "")
    return _run_with_edits(policy, backend, prompt)


def cmd_ask(policy: Policy, backend: BharatCodeBackend, text: str) -> int:
    return _run_with_edits(policy, backend, ASK.format(text=text))


def cmd_undo() -> int:
    res = undo()
    if res.restored:
        console.print(f"[green]Restored[/green] {escape(str(res.path))} from {escape(str(res.backup))}")
    else:
        console.print(
            f"[yellow]No permission to write {escape(str(res.path))}.[/yellow] "
            f"To restore it yourself, run:\n\n  {escape(res.command or '')}\n"
        )
    return 0


def cmd_demo(backend: BharatCodeBackend) -> int:
    dest = pharos_home() / "demo_home"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(Path(__file__).parent / "demo_home", dest)
    policy = sandbox_policy(dest)
    console.print(Panel(
        f"Demo files were copied to [bold]{escape(str(dest))}[/bold].\n"
        "Pharos can only see this folder in demo mode. Your real files are untouched.",
        title="pharos demo",
    ))
    cmd_explain(policy, backend, "sshd_config")
    console.print(
        "\n[bold]Try next[/bold] (same sandbox):\n"
        f"  pharos --root {dest} propose \"disable root login over SSH\"\n"
        f"  pharos --root {dest} why \"my shell takes ages to start\"\n"
        "  pharos undo"
    )
    return 0


# -------------------------------------------------------------------- parser

def _add_common(p: argparse.ArgumentParser, sub: bool) -> None:
    d = argparse.SUPPRESS if sub else None
    p.add_argument("--root", default=d, help="only allow this folder (sandbox)")
    p.add_argument("--model", default=d, help="override the model name")
    p.add_argument(
        "--dry-run", action="store_true", default=argparse.SUPPRESS if sub else False,
        help="show exactly what would be sent to the model, and send nothing",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pharos",
        description="A lighthouse for your Linux configs. Understand your system before you change it.",
        epilog='You can also just type plain words: pharos "why is my wifi dropping"',
    )
    p.add_argument("--version", action="version", version=f"pharos {__version__}")
    _add_common(p, sub=False)
    s = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        sp = s.add_parser(name, help=help_)
        _add_common(sp, sub=True)
        return sp

    add("explain", "explain a config file").add_argument("path")
    add("why", "investigate a symptom (read-only)").add_argument("symptom")
    add("where", "find the file that controls something").add_argument("thing")
    pr = add("propose", "propose a change as a diff; applied only if you approve")
    pr.add_argument("goal")
    pr.add_argument("--file", help="file to start with")
    add("ask", "ask in plain words (same as typing them without a command)").add_argument(
        "text", nargs="+"
    )
    add("undo", "restore the most recent change")
    add("demo", "try Pharos on a safe sample folder")
    return p


def _first_positional(argv: list[str]) -> int | None:
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in _VALUE_FLAGS:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            return i
    return None


def route(argv: list[str]) -> tuple[list[str], str | None]:
    """Turn `pharos some plain words` into `pharos ask some plain words`.

    Returns (argv, suggestion). A suggestion is set when a single word looks like a
    mistyped command, so we can say "did you mean ...?" instead of asking the model.
    """
    i = _first_positional(argv)
    if i is None or argv[i] in COMMANDS:
        return argv, None
    words = argv[i:]
    if len(words) == 1:
        close = difflib.get_close_matches(words[0].lower(), COMMANDS, n=1, cutoff=0.75)
        if close:
            return argv, close[0]
    return argv[:i] + ["ask"] + words, None


def run(args: argparse.Namespace) -> int:
    if args.cmd == "undo":
        return cmd_undo()
    backend = BharatCodeBackend(model=args.model, dry_run=args.dry_run)
    if args.cmd == "demo":
        return cmd_demo(backend)
    policy = sandbox_policy(Path(args.root).expanduser()) if args.root else default_policy()
    if args.cmd == "explain":
        return cmd_explain(policy, backend, args.path)
    if args.cmd == "why":
        return cmd_investigate(policy, backend, WHY, symptom=args.symptom)
    if args.cmd == "where":
        return cmd_investigate(policy, backend, WHERE, thing=args.thing)
    if args.cmd == "ask":
        return cmd_ask(policy, backend, " ".join(args.text))
    return cmd_propose(policy, backend, args.goal, args.file)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv, suggestion = route(argv)
    if suggestion:
        console.print(f"Unknown command. Did you mean [bold]pharos {suggestion}[/bold]?")
        return 2
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except SafetyError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        if "outside the allowed" in str(e):
            console.print(
                "[dim]Pharos only reads dotfiles in ~, ~/.config, ~/.ssh/config and a few "
                "files under /etc.\nTo work in another folder, point Pharos at it, for "
                "example:  pharos --root ~/myfolder explain somefile[/dim]"
            )
        return 2
    except (ModelError, BackupError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
