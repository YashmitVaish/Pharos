# Pharos

> A lighthouse for your Linux configs. **Understand your system before you change it.**

![Pharos Demo](docs/demo.gif)

Pharos is an AI-powered Linux configuration assistant for Ubuntu. It helps you understand your system, investigate configuration issues, and safely make changes without blindly modifying files.

It explains configuration files in plain English, investigates problems using read-only tools, and proposes targeted fixes through reviewable diffs.

**No blind edits. No unrestricted shell access. No changes without your approval.**

Built for the [BharatCode Build League](https://bharatcode.ai), powered by the BharatCode model API (`qwen-3.8-27b`).

---

## See Pharos in Action

### 1. Configuration Understanding

Pharos explains configuration files and individual settings in plain English, including shell history, terminal behaviour, environment settings, and more.

![Bash Configuration Explanation](docs/screenshots/01-bashrc-explanation.png)

### 2. Configuration Discovery

Finds and explains the configuration file responsible for a particular system setting.

![Git Configuration Discovery](docs/screenshots/03-git-config-discovery.png)

### 3. Security Boundaries

Sensitive system files are blocked, even when explicitly requested.

![Sensitive File Access Blocked](docs/screenshots/04-shadow-access-blocked.png)

### 4. Safe Configuration Changes

Every proposed modification is displayed as a diff before approval. Changes are backed up and can be reverted using `pharos undo`.

![Safe SSH Configuration Edit](docs/screenshots/04-safe-ssh-edit-and-undo.png)

---

## Try it in 10 seconds (no risk)

```bash
git clone https://github.com/YashmitVaish/pharos && cd pharos
uv sync
export BHARATCODE_API_KEY="your-key"
uv run pharos demo
```

`pharos demo` copies sample files (an SSH config, a shell config, and an fstab) to `~/.pharos/demo_home` and works only inside that folder. Your real files are never touched.

Want to see what would leave your machine first? Add `--dry-run`: Pharos prints the exact request and sends nothing.

```bash
uv run pharos --dry-run demo
```

---

## Commands

| Command | What it does |
| --- | --- |
| `pharos explain <path>` | Explains each setting in a file and flags risky ones |
| `pharos why "<symptom>"` | Reads configs and logs (read-only) and explains the likely cause |
| `pharos where "<thing>"` | Finds and explains the file that controls something |
| `pharos propose "<goal>"` | Shows a diff with a reason; applies it only after you confirm |
| `pharos undo` | Restores the most recent change from its backup |
| `pharos demo` | Runs on a safe sample folder |
| `pharos <plain words>` | Natural-language interface; for example, `pharos "why is my terminal slow to start"` |

Options: `--dry-run`, `--root <folder>` (sandbox: Pharos can only see that folder), `--model <name>`.

---

## Built for Ubuntu

A general AI model can be confidently wrong about version-specific Ubuntu behaviour, so Pharos does not rely solely on its training data.

- **It knows your machine.** Every request carries one line such as the Ubuntu version, codename, kernel and init system (no hostname, username or IP).
- **It reads the real manual.** The `man_page` tool returns the man page installed on your system (filtered by keyword), and `package_version` returns installed versions.
- **Curated Ubuntu notes.** Notes are attached when Pharos reads a matching file. They cover common traps, such as SSH drop-ins in `sshd_config.d` overriding the main file, `ssh.socket` on 24.04 ignoring a `Port` change until `daemon-reload`, the deb822 `ubuntu.sources` format, and `netplan try` before `netplan apply`. The notes live in `src/pharos/notes/*.md` with their sources in comments, and can be reviewed and extended by anyone.
- **Validation guidance.** After a proposed change, Pharos prints the relevant validation command (for example, `sudo sshd -t`).

---

## Safety Model

Safety is the main feature, not an add-on.

1. **Read-only by default.** Every write needs your approval of a diff.
2. **Diff first.** Every change is a unified diff with a one-line reason.
3. **Backups and undo.** A timestamped copy goes to `~/.pharos/backups/` before any write; `pharos undo` restores it exactly (bytes and permissions).
4. **Path allowlist.** Only approved places can be read or changed: `~/.config`, dotfiles directly in `~`, `~/.ssh/config`, and specific files and folders under `/etc` (ssh, apt, systemd, netplan, fstab, hosts and a few others). Symlinks are resolved and `..` is neutralised before the check.
5. **Hard deny list.** Private keys, `.env` files, `.gnupg`, `.aws`, browser profiles, `/etc/shadow` and similar are never readable, even inside the allowlist.
6. **Secrets stay local.** Passwords, tokens, private keys and URL credentials are redacted before anything is sent to the API. Redacted values show as `[REDACTED]`, and Pharos refuses edits that touch them.
7. **No privilege escalation.** Pharos never runs `sudo`. If a file needs root, it saves the proposed file and prints the exact `sudo cp ...` command for you to read and run yourself.
8. **No free shell.** The model has a fixed set of tools: `list_dir`, `read_file`, `search_files`, `service_status`, `journal_tail`, `man_page`, `package_version` and `propose_edit`. Names are validated and commands run without a shell.
9. **Files are data, not instructions.** The system prompt tells the model to ignore instructions found inside files and logs.
10. **Size caps.** Limits apply to file reads (64 KB), search results and command output.

Access is determined by Pharos's own path and file restrictions, not simply by whether the current Linux user has permission to read a file.

Redaction, the allowlist, the tool layer, backups and undo are covered by tests:

```bash
uv run pytest
```

---

## How it Uses BharatCode

All reasoning goes through the BharatCode chat API (OpenAI-compatible, with tool calling).

Pharos sends redacted file contents and tool results, and the model answers or calls tools. The model sits behind one small interface (`src/pharos/model.py`), so another backend can be swapped in without changing the rest of the application.

---

## Install

Requires Python 3.10+ and Ubuntu. Other Debian-based systems should work but are currently untested.

```bash
pipx install git+https://github.com/YashmitVaish/pharos
```

### Configuration

Configuration is read from environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `BHARATCODE_API_KEY` | Your BharatCode API key | None (required) |
| `BHARATCODE_BASE_URL` | API base URL | `https://bharatcode.ai/api/model/v1` |
| `BHARATCODE_MODEL` | Model name | `qwen-3.8-27b` |

Never commit API keys. Keep `.env` files out of version control and use environment variables for credentials.

---

## Development

```bash
uv sync
uv run pytest
uv run --env-file .env python scripts/api_check.py
```

The API check script smoke-tests your configured API credentials.

### Project Structure

```text
src/pharos/
├── cli.py        # CLI commands
├── model.py      # BharatCode backend + tool loop
├── tools.py      # Model tools
├── safety.py     # Allowlist, deny rules, redaction
├── backup.py     # Backups and undo
├── prompts.py    # System prompts
├── notes/        # Curated Ubuntu notes
└── demo_home/    # Sample files for pharos demo

tests/
docs/
├── demo.gif
└── screenshots/
```

---

## Limitations

- AI can be wrong. Read every diff before you approve it.
- Pharos is not a substitute for real backups of important systems.
- Edits are exact text replacements; very large files (over 64 KB) are not edited.
- Dotfiles that are symlinks into another folder (for example, a dotfiles repo) are blocked because the real path is outside the allowlist.
- Tested on Ubuntu 26.04 only. Other distributions have not been verified.

---

## Roadmap

- `--learn` mode that adds a one-line lesson to each change.
- Dotfile doctor: dead aliases and slow startup lines in `.bashrc` and `.zshrc`.
- Config time machine over the backup history.

---

## License

MIT. See [LICENSE](LICENSE).

## Credits

Built by Yashmit Vaish for the BharatCode Build League.

Model calls by BharatCode. Optional small-model training by Adaption.
