# ufw (firewall)
- Before `sudo ufw enable` on a remote machine, allow SSH first (`sudo ufw allow OpenSSH` or `sudo ufw allow 22/tcp`), or the user can lock themselves out.
- The usual defaults are deny incoming, allow outgoing. Check with `sudo ufw status verbose`.
- Change rules with `ufw allow` / `ufw deny`, not by editing `/etc/ufw/*.rules` by hand.
- Docker publishes ports by editing iptables directly and can bypass ufw rules.
