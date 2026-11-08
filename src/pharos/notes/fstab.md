# /etc/fstab
- A bad entry can stop normal boot (the system may drop to emergency mode). Check with `sudo findmnt --verify`, and test with `sudo mount -a` before rebooting.
- Prefer `UUID=` (see `lsblk -f` or `blkid`) over `/dev/sdX` names, which can change.
- For non-essential drives and network shares add `nofail` so a missing device does not block boot. For network shares also consider `_netdev` or `x-systemd.automount`.
- Do not put passwords in fstab. For CIFS use a `credentials=` file with mode 600.
- The last two numbers are dump (usually 0) and fsck order (1 for `/`, 2 for other filesystems, 0 for none).
