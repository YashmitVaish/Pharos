# Pharos

> A lighthouse for your Linux configs. **Understand your system before you change it.**

<!-- TODO: replace with a real 20-second GIF: `pharos demo`, then `pharos propose` and an approved diff -->
![Pharos demo](docs/demo.gif)

Pharos is a lightweight AI helper for your Ubuntu terminal. It reads your config files, explains every setting, investigates problems read-only, and proposes fixes as diffs. It never changes a file without a visible diff, a backup and your explicit yes.

Built for the [BharatCode Build League](https://bharatcode.ai) on the BharatCode model API (`qwen-3.8-27b`).

## Try it in 10 seconds (no risk)

```bash
git clone https://github.com/YashmitVaish/pharos && cd pharos
uv sync
export BHARATCODE_API_KEY="your-key"
uv run pharos demo
```

`pharos demo` copies sample files (an SSH config, a shell config, an fstab) to `~/.pharos/demo_home` and works only inside that folder. Your real files are never touched.

Want to see what would leave your machine first? Add `--dry-run`: Pharos prints the exact request and sends nothing.

```bash
uv run pharos --dry-run demo
```

## Commands

| Command | What it does |
| --- | --- |
| `pharos explain <path>` | Explains each setting in a file and flags risky ones |
| `pharos why "<symptom>"` | Reads configs and logs (read-only) and explains the likely cause |
| `pharos where "<thing>"` | Finds and explains the file that controls something |
| `pharos propose "<goal>"` | Shows a diff with a reason; applies it only after you confirm |
| `pharos undo` | Restores the most recent change from its backup |
| `pharos demo` | Runs on a safe sample folder |

Options: `--dry-run`, `--root <folder>` (sandbox: Pharos can only see that folder), `--model <name>`.

<!-- TODO: paste a real terminal session here once recorded -->

## Safety model

Safety is the main feature, not an add-on.

1. **Read-only by default.** Every write needs your approval of a diff.
2. **Diff first.** Every change is a unified diff with a one-line reason.
3. **Backups and undo.** A timestamped copy goes to `~/.pharos/backups/` before any write; `pharos undo` restores it exactly (bytes and permissions).
4. **Path allowlist.** Only approved places can be read or changed: `~/.config`, dotfiles directly in `~`, `~/.ssh/config`, and specific files and folders under `/etc` (ssh, apt, systemd, netplan, fstab, hosts and a few others). Symlinks are resolved and `..` is neutralised before the check.
5. **Hard deny list.** Private keys, `.env` files, `.gnupg`, `.aws`, browser profiles, `/etc/shadow` and similar are never readable, even inside the allowlist.
6. **Secrets stay local.** Passwords, tokens, private keys and URL credentials are redacted before anything is sent to the API. Redacted values show as `[REDACTED]`, and Pharos refuses edits that touch them.
7. **No privilege escalation.** Pharos never runs `sudo`. If a file needs root, it saves the proposed file and prints the exact `sudo cp ...` command for you to read and run yourself.
8. **No free shell.** The model has a fixed set of tools: `list_dir`, `read_file`, `search_files`, `service_status`, `journal_tail` and `propose_edit`. Service names are validated and commands run without a shell.
9. **Files are data, not instructions.** The system prompt tells the model to ignore instructions found inside files and logs.
10. **Size caps** on file reads (64 KB), search results and command output.

Redaction, the allowlist, the tool layer, backups and undo are covered by tests: `uv run pytest`.

## How it uses BharatCode

All reasoning goes through the BharatCode chat API (OpenAI-compatible, with tool calling). Pharos sends redacted file contents and tool results, and the model answers or calls tools. The model sits behind one small interface (`src/pharos/model.py`) so another backend can be swapped in.


## Install

Requires Python 3.10+ and Ubuntu (other Debian-based systems should work but are untested).

```bash
pipx install git+https://github.com/YashmitVaish/pharos
```

Configuration is read from environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `BHARATCODE_API_KEY` | Your BharatCode API key | none (required) |
| `BHARATCODE_BASE_URL` | API base URL | `https://bharatcode.ai/api/model/v1` |
| `BHARATCODE_MODEL` | Model name | `qwen-3.8-27b` |

Never commit keys. This repository contains no secrets; `.env` is git-ignored.

## Development

```bash
uv sync
uv run pytest
uv run --env-file .env python scripts/api_check.py   # smoke-test your API key
```

```
src/pharos/
  cli.py        commands
  model.py      BharatCode backend + tool loop
  tools.py      the model's tools
  safety.py     allowlist, deny rules, redaction
  backup.py     backups and undo
  prompts.py    system prompts
  demo_home/    sample files for `pharos demo`
tests/
```

## Limitations

- AI can be wrong. Read every diff before you approve it.
- Pharos is not a substitute for real backups of important systems.
- Edits are exact text replacements; very large files (over 64 KB) are not edited.
- Dotfiles that are symlinks into another folder (for example a dotfiles repo) are blocked, because the real path is outside the allowlist.
- Tested on Ubuntu only. <!-- TODO: state the versions you tested -->

## Roadmap

- `--learn` mode that adds a one-line lesson to each change
- Dotfile doctor: dead aliases and slow startup lines in `.bashrc` and `.zshrc`
- Config time machine over the backup history

## License

MIT. See [LICENSE](LICENSE).

## Credits

Built by Yashmit Vaish for the BharatCode Build League. Model calls by BharatCode. Optional small-model training by Adaption.
