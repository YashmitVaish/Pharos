from pathlib import Path

import pytest

from pharos.safety import (
    Policy, SafetyError, default_policy, redact, sandbox_policy,
)


# ---------------------------------------------------------------- redaction

def test_redacts_key_value_secrets():
    text = "password: hunter2\nexport API_TOKEN=abc123\nPort 22\n"
    out, n = redact(text)
    assert "hunter2" not in out and "abc123" not in out
    assert "Port 22" in out
    assert n == 2


def test_does_not_redact_ssh_directives():
    out, n = redact("PasswordAuthentication no\nPermitRootLogin yes\n")
    assert n == 0
    assert "PasswordAuthentication no" in out


def test_redacts_private_key_blocks():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAB3Nza\n-----END OPENSSH PRIVATE KEY-----"
    out, n = redact("before\n" + pem + "\nafter")
    assert "AAAAB3Nza" not in out
    assert "before" in out and "after" in out and n == 1


def test_redacts_url_credentials_and_bearer():
    out, _ = redact("url = https://bob:s3cret@example.com/x\nAuthorization: Bearer abcdefghijklmnop1234")
    assert "s3cret" not in out
    assert "abcdefghijklmnop1234" not in out


def test_redacts_known_token_shapes():
    out, n = redact("a ghp_" + "A" * 30 + " b AKIA" + "B" * 16 + " c sk-" + "c" * 24)
    assert n == 3
    assert "ghp_" not in out and "AKIA" not in out and "sk-" not in out


# ---------------------------------------------------------------- allowlist

@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    (h / ".config" / "app").mkdir(parents=True)
    (h / ".config" / "app" / "conf").write_text("x=1")
    (h / ".ssh").mkdir()
    (h / ".ssh" / "id_rsa").write_text("PRIVATE")
    (h / ".ssh" / "config").write_text("Host *")
    (h / ".bashrc").write_text("alias ll=ls")
    (h / "notes.txt").write_text("not a dotfile")
    return h.resolve()


def test_allows_dotfile_config_dir_and_ssh_config(home):
    p = default_policy(home)
    assert p.resolve(home / ".bashrc") == home / ".bashrc"
    assert p.resolve("~/.config/app/conf") == home / ".config" / "app" / "conf"
    assert p.resolve("~/.ssh/config") == home / ".ssh" / "config"


def test_blocks_private_keys(home):
    p = default_policy(home)
    with pytest.raises(SafetyError):
        p.resolve(home / ".ssh" / "id_rsa")


def test_blocks_non_dotfiles_in_home(home):
    with pytest.raises(SafetyError):
        default_policy(home).resolve(home / "notes.txt")


def test_blocks_system_secrets_and_outside_paths(home):
    p = default_policy(home)
    for bad in ("/etc/shadow", "/etc/passwd", "/root/.bashrc", "/tmp/x"):
        with pytest.raises(SafetyError):
            p.resolve(bad)


def test_blocks_dotdot_traversal(home):
    p = default_policy(home)
    with pytest.raises(SafetyError):
        p.resolve(home / ".config" / ".." / ".ssh" / "id_rsa")


def test_blocks_symlink_escape(home):
    link = home / ".config" / "link"
    link.symlink_to(home / ".ssh" / "id_rsa")
    with pytest.raises(SafetyError):
        default_policy(home).resolve(link)


def test_home_listing_allowed_but_home_read_is_not(home):
    p = default_policy(home)
    assert p.resolve("~", listing=True) == home
    with pytest.raises(SafetyError):
        p.resolve("~")


def test_sandbox_only_allows_its_root(tmp_path):
    root = tmp_path / "box"
    root.mkdir()
    (root / "a.conf").write_text("x")
    p = sandbox_policy(root)
    assert p.resolve("a.conf") == (root / "a.conf").resolve()
    with pytest.raises(SafetyError):
        p.resolve("/etc/hostname")


def test_sandbox_still_applies_deny_rules(tmp_path):
    root = tmp_path / "box"
    root.mkdir()
    (root / "id_rsa").write_text("k")
    with pytest.raises(SafetyError):
        sandbox_policy(root).resolve("id_rsa")
