# Security

Pharos reads configuration files and sends redacted content to a model API, so safety bugs matter.

Please report problems privately by opening a GitHub security advisory on this repository (Security tab, "Report a vulnerability"), or by email to the maintainer if an advisory is not possible.

Examples worth reporting:

- A way to read or edit a path outside the allowlist, or a file on the deny list
- A secret that reaches the API request unredacted (check with `pharos --dry-run`)
- A way to make Pharos run a command, or run `sudo`
- A way to change a file without the diff and approval step

Known limits: redaction is pattern-based and will miss unusual secret formats. Review `--dry-run` output if your files hold anything sensitive.
