from pharos.cli import build_parser, main


def test_options_work_before_and_after_subcommand():
    p = build_parser()
    a = p.parse_args(["--dry-run", "explain", "x"])
    b = p.parse_args(["explain", "x", "--dry-run"])
    assert a.dry_run and b.dry_run
    assert not p.parse_args(["explain", "x"]).dry_run
    assert p.parse_args(["--root", "/tmp/r", "why", "slow"]).root == "/tmp/r"
    assert p.parse_args(["why", "slow", "--root", "/tmp/r"]).root == "/tmp/r"


def test_dry_run_explain_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PHAROS_HOME", str(tmp_path / "ph"))
    monkeypatch.delenv("BHARATCODE_API_KEY", raising=False)
    (tmp_path / "sshd_config").write_text("PermitRootLogin yes\ntoken = abc123\n")
    code = main(["--dry-run", "--root", str(tmp_path), "explain", "sshd_config"])
    out = capsys.readouterr().out
    assert code == 0
    assert "PermitRootLogin yes" in out
    assert "abc123" not in out


def test_blocked_path_exits_with_code_2(tmp_path, capsys):
    code = main(["--dry-run", "--root", str(tmp_path), "explain", "/etc/shadow"])
    assert code == 2
    assert "Blocked" in capsys.readouterr().out


def test_demo_dry_run_copies_files_and_sends_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PHAROS_HOME", str(tmp_path / "ph"))
    monkeypatch.delenv("BHARATCODE_API_KEY", raising=False)
    code = main(["--dry-run", "demo"])
    assert code == 0
    assert (tmp_path / "ph" / "demo_home" / "sshd_config").exists()
    assert "Dry run" in capsys.readouterr().out
