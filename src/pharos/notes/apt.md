# apt sources on Ubuntu
<!-- sources: https://discourse.ubuntu.com/t/spec-apt-deb822-sources-by-default/29333 -->
- Since Ubuntu 24.04 the main Ubuntu sources live in `/etc/apt/sources.list.d/ubuntu.sources` (deb822 format: `Types:`, `URIs:`, `Suites:`, `Components:`, `Signed-By:` stanzas). `/etc/apt/sources.list` may be nearly empty. Older releases use one-line `deb ...` entries in `/etc/apt/sources.list`.
- Third-party repositories should use a `Signed-By` keyring (for example under `/etc/apt/keyrings/`). Do not use the deprecated `apt-key`.
- After any change run `sudo apt update` and read the errors before installing anything.
- Do not remove the `-updates` or `-security` suites.
