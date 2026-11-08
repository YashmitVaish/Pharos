from pathlib import Path

import pytest

from pharos.safety import MAX_READ_BYTES, sandbox_policy
from pharos.tools import ToolBox


@pytest.fixture
def box(tmp_path: Path) -> Path:
    root = tmp_path / "box"
    root.mkdir()
    (root / "sshd_config").write_text(
        "PermitRootLogin yes\nPasswordAuthentication yes\npassword: hunter2\n"
    )
    (root / "id_rsa").write_text("PRIVATE")
    return root


def tb(root: Path, edit: bool = False) -> ToolBox:
    return ToolBox(sandbox_policy(root), allow_edit=edit)


def test_read_file_redacts_and_reports(box):
    out = tb(box).call("read_file", {"path": "sshd_config"})
    assert "hunter2" not in out
    assert "[REDACTED]" in out and "redacted" in out
    assert "PermitRootLogin yes" in out


def test_read_file_blocked_paths_return_error_text_not_exception(box):
    t = tb(box)
    assert t.call("read_file", {"path": "id_rsa"}).startswith("error:")
    assert t.call("read_file", {"path": "../outside"}).startswith("error:")
    assert t.call("read_file", {"path": "/etc/passwd"}).startswith("error:")


def test_read_file_truncates_large_files(box):
    (box / "big").write_text("a" * (MAX_READ_BYTES + 500))
    out = tb(box).call("read_file", {"path": "big"})
    assert "truncated" in out
    assert len(out) < MAX_READ_BYTES + 300


def test_list_dir_hides_denied_entries(box):
    out = tb(box).call("list_dir", {"path": "."})
    assert "sshd_config" in out
    assert "id_rsa" not in out


def test_search_files_redacts_and_skips_denied(box):
    out = tb(box).call("search_files", {"query": "password"})
    assert "hunter2" not in out
    assert "sshd_config" in out
    assert "id_rsa" not in tb(box).call("search_files", {"query": "PRIVATE"})


def test_unknown_tool_and_edit_tool_disabled_by_default(box):
    t = tb(box)
    assert t.call("rm_rf", {}).startswith("error: unknown tool")
    assert t.call("propose_edit", {"path": "sshd_config", "old_text": "a", "new_text": "b", "reason": "r"}).startswith("error: unknown tool")


def test_propose_edit_records_diff_and_does_not_write(box):
    t = tb(box, edit=True)
    before = (box / "sshd_config").read_text()
    out = t.call("propose_edit", {
        "path": "sshd_config",
        "old_text": "PermitRootLogin yes",
        "new_text": "PermitRootLogin no",
        "reason": "Disable root login.",
    })
    assert out.startswith("Proposal recorded")
    assert (box / "sshd_config").read_text() == before  # nothing written
    assert "-PermitRootLogin yes" in t.proposals[0].diff
    assert "+PermitRootLogin no" in t.proposals[0].diff


def test_propose_edit_requires_exactly_one_match(box):
    t = tb(box, edit=True)
    base = {"path": "sshd_config", "new_text": "x", "reason": "r"}
    assert "matched 0" in t.call("propose_edit", {**base, "old_text": "nope"})
    assert "matched 2" in t.call("propose_edit", {**base, "old_text": "yes"})


def test_propose_edit_refuses_redacted_text(box):
    t = tb(box, edit=True)
    out = t.call("propose_edit", {
        "path": "sshd_config", "old_text": "password: [REDACTED]",
        "new_text": "password: x", "reason": "r",
    })
    assert out.startswith("error:") and not t.proposals


def test_propose_edit_blocked_on_denied_path(box):
    t = tb(box, edit=True)
    out = t.call("propose_edit", {"path": "id_rsa", "old_text": "PRIVATE", "new_text": "x", "reason": "r"})
    assert out.startswith("error:") and not t.proposals


def test_second_proposal_builds_on_first(box):
    t = tb(box, edit=True)
    t.call("propose_edit", {"path": "sshd_config", "old_text": "PermitRootLogin yes", "new_text": "PermitRootLogin no", "reason": "a"})
    t.call("propose_edit", {"path": "sshd_config", "old_text": "PasswordAuthentication yes", "new_text": "PasswordAuthentication no", "reason": "b"})
    final = next(iter(t.final_texts().values()))
    assert "PermitRootLogin no" in final and "PasswordAuthentication no" in final


def test_service_names_are_validated(box):
    t = tb(box)
    assert "invalid unit" in t.call("service_status", {"unit": "ssh; rm -rf /"})
    assert "invalid unit" in t.call("journal_tail", {"unit": "$(id)"})
