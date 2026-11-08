# netplan on Ubuntu
<!-- sources: https://linuxize.com/post/how-to-configure-networking-with-netplan-on-ubuntu/ -->
- Files in `/etc/netplan/*.yaml` are read in alphanumeric order; later files override earlier ones.
- YAML uses spaces only, never tabs. Wrong indentation is the most common failure.
- Prefer `sudo netplan try` (rolls back automatically unless confirmed) over `sudo netplan apply`, especially over SSH. `sudo netplan generate` checks the config without touching the live network.
- Files should be mode 600 (root only). Wi-Fi passwords in these files are stored in plain text.
- Ubuntu Desktop usually uses `renderer: NetworkManager`, so Wi-Fi is normally managed in the system settings, not in netplan.
