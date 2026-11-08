from pathlib import Path

import pytest

from pharos.notes import NOTES_DIR, note_name, notes_for
from pharos.prompts import system_prompt
from pharos.safety import sandbox_policy
from pharos.sysinfo import describe, parse_os_release
from pharos.tools import NOTES_MARKER, ToolBox

UBUNTU_2404 = """\
PRETTY_NAME="Ubuntu 24.04.1 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
ID=ubuntu
ID_LIKE=debian
VERSION_CODENAME=noble
"""


# ------------------------------------------------------------------ sysinfo

def test_parse_os_release_strips_quotes_and_comments():
    info = parse_os_release('# c\nID=ubuntu\nPRETTY_NAME="Ubuntu 24.04"\nbad line\n')
    assert info == {"ID": "ubuntu", "PRETTY_NAME": "Ubuntu 24.04"}


def test_describe_ubuntu_has_version_codename_and_no_warning():
    line = describe(parse_os_release(UBUNTU_2404))
    assert "Ubuntu 24.04.1 LTS" in line and "noble" in line and "kernel" in line
    assert "not Ubuntu" not in line


def test_describe_warns_on_non_ubuntu():
    line = describe({"ID": "fedora", "PRETTY_NAME": "Fedora Linux 40"})
    assert "Fedora Linux 40" in line and "not Ubuntu" in line


def test_describe_survives_missing_os_release():
    assert "not Ubuntu" in describe({})


def test_system_prompt_includes_machine_line():
    assert "This machine:" in system_prompt()


# -------------------------------------------------------------------- notes

@pytest.mark.parametrize("path,expected", [
    ("/etc/ssh/sshd_config", "ssh"),
    ("/etc/ssh/sshd_config.d/50-cloud-init.conf", "ssh"),
    ("/etc/netplan/01-netcfg.yaml", "netplan"),
    ("/etc/netplan/readme.txt", None),
    ("/etc/apt/sources.list", "apt"),
    ("/etc/apt/sources.list.d/ubuntu.sources", "apt"),
    ("/etc/fstab", "fstab"),
    ("/etc/default/ufw", "ufw"),
    ("/etc/ufw/before.rules", "ufw"),
    ("/etc/sysctl.d/99-local.conf", "sysctl"),
    ("/home/u/.bashrc", "shell"),
    ("/home/u/.profile", "shell"),
    ("/home/u/.config/app/conf", None),
    ("/tmp/demo/bashrc", "shell"),  # demo files have no leading dot
])
def test_note_matching(path, expected):
    assert note_name(Path(path)) == expected


def test_every_note_file_exists_and_is_nonempty():
    for key in ("ssh", "netplan", "apt", "fstab", "ufw", "sysctl", "shell"):
        text = (NOTES_DIR / f"{key}.md").read_text()
        assert len(text) > 200, key


def test_html_comments_with_sources_are_not_sent():
    text = notes_for(Path("/etc/ssh/sshd_config"))
    assert "<!--" not in text and "launchpad" not in text
    assert "50-cloud-init" in text and "ssh.socket" in text


def test_read_file_appends_notes_for_known_files(tmp_path):
    (tmp_path / "sshd_config").write_text("PermitRootLogin yes\n")
    (tmp_path / "random.conf").write_text("a=1\n")
    tb = ToolBox(sandbox_policy(tmp_path))
    assert NOTES_MARKER in tb.call("read_file", {"path": "sshd_config"})
    assert NOTES_MARKER not in tb.call("read_file", {"path": "random.conf"})


# ------------------------------------------------------------ man / packages

def test_man_and_package_names_are_validated(tmp_path):
    tb = ToolBox(sandbox_policy(tmp_path))
    assert "invalid man page name" in tb.call("man_page", {"name": "ls; rm -rf /"})
    assert "invalid man page name" in tb.call("man_page", {"name": "../../etc/passwd"})
    assert "section must be" in tb.call("man_page", {"name": "ls", "section": "9; id"})
    assert "invalid package name" in tb.call("package_version", {"name": "bash; id"})
    assert "invalid package name" in tb.call("package_version", {"name": "$(id)"})


def test_man_output_is_cleaned_and_filtered_by_query(tmp_path, monkeypatch):
    raw = (
        "SSHD_CONFIG(5)\n\n"
        "P\x08PE\x08ER\x08RM\x08MI\x08IT\x08TR\x08RO\x08OO\x08OT\x08TL\x08LO\x08OG\x08GI\x08IN\x08N\n"
        "       Specifies whether root can log in using ssh(1).\n\n"
        "\x1b[1mPort\x1b[0m\n       Specifies the port number.\n"
    )
    tb = ToolBox(sandbox_policy(tmp_path))
    monkeypatch.setattr(ToolBox, "_exec", lambda self, argv, env=None: (0, raw))
    out = tb.call("man_page", {"name": "sshd_config", "section": "5", "query": "permitrootlogin"})
    assert "PERMITROOTLOGIN" in out and "\x08" not in out and "\x1b" not in out
    assert "port number" not in out
    miss = tb.call("man_page", {"name": "sshd_config", "query": "nonexistent"})
    assert "no paragraph mentions" in miss


def test_man_missing_page_is_reported_as_error(tmp_path, monkeypatch):
    tb = ToolBox(sandbox_policy(tmp_path))
    monkeypatch.setattr(ToolBox, "_exec", lambda self, argv, env=None: (16, "No manual entry for nope"))
    assert tb.call("man_page", {"name": "nope"}).startswith("error: No manual entry")


def test_man_uses_fixed_argv_without_a_shell(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(ToolBox, "_exec", lambda self, argv, env=None: seen.update(argv=argv) or (0, "x"))
    ToolBox(sandbox_policy(tmp_path)).call("man_page", {"name": "sshd_config", "section": "5"})
    assert seen["argv"] == ["man", "-P", "cat", "5", "sshd_config"]


def test_package_version_reports_missing(tmp_path, monkeypatch):
    tb = ToolBox(sandbox_policy(tmp_path))
    monkeypatch.setattr(ToolBox, "_exec", lambda self, argv, env=None: (1, "no packages found"))
    assert "not installed" in tb.call("package_version", {"name": "nopkg"})
