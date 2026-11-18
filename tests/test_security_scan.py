from app.agent.security_scan import run_local_security_scan


def test_local_scan_detects_common_risky_patterns_without_echoing_secret(tmp_path):
    (tmp_path / "backend").mkdir()
    fake_secret = "sk-proj-" + "abcdefghijklmnopqrstuvwxyz123456"
    (tmp_path / "backend" / "config.py").write_text(
        'API_KEY = "' + fake_secret + '"\n'
        "requests.get(url, verify=False)\n"
        "subprocess.run(command, shell=True)\n",
        encoding="utf-8",
    )
    (tmp_path / "frontend.js").write_text(
        'element.innerHTML = userInput;\n',
        encoding="utf-8",
    )

    result = run_local_security_scan(tmp_path)

    findings = {(finding.rule_id, finding.file_path, finding.line) for finding in result.findings}
    assert ("hardcoded-credential", "backend/config.py", 1) in findings
    assert ("tls-verification-disabled", "backend/config.py", 2) in findings
    assert ("shell-command-execution", "backend/config.py", 3) in findings
    assert result.scanned_files == 2
    assert fake_secret not in str(result.model_dump())
    assert result.high_count == 3


def test_local_scan_excludes_environment_and_generated_directories(tmp_path):
    fake_secret = "sk-proj-" + "abcdefghijklmnopqrstuvwxyz123456"
    (tmp_path / "app.py").write_text("print('safe')\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        'API_KEY="' + fake_secret + '"\n',
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text("API_KEY=\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.js").write_text(
        "eval(userInput)\n",
        encoding="utf-8",
    )
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "settings.json").write_text(
        '{"token": "private-value-that-should-not-be-read"}',
        encoding="utf-8",
    )

    result = run_local_security_scan(tmp_path)

    assert result.scanned_files == 1
    assert result.findings == []
    assert result.skipped_files >= 2


def test_local_scan_reports_wildcard_cors_and_dynamic_execution(tmp_path):
    (tmp_path / "config.py").write_text(
        'allow_origins = ["*"]\n'
        "result = eval(expression)\n",
        encoding="utf-8",
    )

    result = run_local_security_scan(tmp_path)

    assert [finding.rule_id for finding in result.findings] == [
        "wildcard-cors",
        "dynamic-code-execution",
    ]


def test_local_scan_finds_python_ast_risks_and_ignores_safe_or_documentation_examples(tmp_path):
    (tmp_path / "app.py").write_text(
        "import pickle\n"
        "import yaml\n"
        "def load(raw, cursor, user_id):\n"
        "    pickle.loads(raw)\n"
        "    yaml.load(raw)\n"
        "    yaml.load(raw, Loader=yaml.SafeLoader)\n"
        '    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n'
        '    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))\n'
        "    subprocess.run(command, shell=True)\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "Example only: subprocess.run(command, shell=True)\n",
        encoding="utf-8",
    )

    result = run_local_security_scan(tmp_path)

    findings = {(finding.rule_id, finding.line) for finding in result.findings}
    assert findings == {
        ("unsafe-deserialization", 4),
        ("unsafe-yaml-load", 5),
        ("dynamic-sql", 7),
        ("shell-command-execution", 9),
    }


def test_local_scan_matches_multiline_configuration_rules(tmp_path):
    (tmp_path / "config.py").write_text(
        "allow_origins = [\n"
        '    "*",\n'
        "]\n",
        encoding="utf-8",
    )

    result = run_local_security_scan(tmp_path)

    assert [(finding.rule_id, finding.line) for finding in result.findings] == [
        ("wildcard-cors", 1),
    ]
