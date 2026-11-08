# sysctl
- Persistent kernel settings go in `/etc/sysctl.d/*.conf` (preferred) or `/etc/sysctl.conf`. Files are applied in lexical order; for the same key a later file overrides an earlier one.
- Apply without rebooting: `sudo sysctl --system`. Check one value: `sysctl <key>`.
- Prefer a new file such as `/etc/sysctl.d/99-local.conf` over editing distribution files.
- Change one setting at a time and note the old value so it can be reverted.
