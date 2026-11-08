# Shell startup files (bash on Ubuntu)
- New terminal windows (interactive non-login shells) read `~/.bashrc`. Login shells read `~/.profile` (or `~/.bash_profile` if it exists). Ubuntu's default `~/.profile` sources `~/.bashrc` and adds `~/bin` and `~/.local/bin` to PATH if they exist.
- Put aliases and prompt settings in `~/.bashrc` (or `~/.bash_aliases`, which the default `~/.bashrc` loads if present). Put PATH and environment variables in `~/.profile`.
- Slow terminal startup usually comes from commands that run every time: `eval "$(...)"`, `nvm.sh`, `kubectl completion`, `conda init`. Time them or load them lazily.
- If an alias is defined twice, the last definition wins. Repeated PATH entries are harmless but untidy.
- Test an edit in a new terminal or with `source ~/.bashrc`. Pharos keeps a backup of the old file.
