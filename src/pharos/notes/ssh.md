# sshd on Ubuntu
<!-- sources:
  https://bugs.launchpad.net/ubuntu/+source/openssh/+bug/2069041  (24.04 socket activation, Port changes)
  https://lists.snapcraft.io/archives/foundations-bugs/2024-November/527297.html  (cloud-init 50-cloud-init.conf)
  sshd_config(5): "for each keyword, the first obtained value will be used"
-->
- `/etc/ssh/sshd_config` starts with `Include /etc/ssh/sshd_config.d/*.conf`. For most keywords the FIRST value sshd reads wins (see sshd_config(5)), so a drop-in file can silently override the main file. Always check `/etc/ssh/sshd_config.d/` too.
- Cloud images often have `/etc/ssh/sshd_config.d/50-cloud-init.conf` containing `PasswordAuthentication yes`. To turn password login off, change that drop-in (or add an earlier-sorting file such as `00-hardening.conf`), not only the main file.
- On Ubuntu 24.04, ssh is socket-activated. Changing `Port` may not take effect until `sudo systemctl daemon-reload && sudo systemctl restart ssh.socket`. Check with `service_status("ssh.socket")`.
- Validate before restarting: `sudo sshd -t`. On Ubuntu the service is normally called `ssh`: `sudo systemctl reload ssh`.
- Before disabling password login or root login, confirm key-based login works, and keep a second SSH session open until a fresh login succeeds.
- Usual hardening targets: `PermitRootLogin no` (or `prohibit-password`), `PasswordAuthentication no`, a lower `MaxAuthTries`.
