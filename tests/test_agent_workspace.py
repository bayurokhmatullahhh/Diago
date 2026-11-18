import pytest
from fastapi import HTTPException

from app.agent import workspace


def test_workspace_lists_only_supported_non_secret_source_files(tmp_path, monkeypatch):
    root = tmp_path
    fake_secret = "sk-proj-" + "abcdefghijklmnopqrstuvwxyz123456"
    (root / "backend").mkdir()
    (root / "backend" / "main.py").write_text("print('safe')", encoding="utf-8")
    (root / "backend" / ".hidden.py").write_text("print('hidden')", encoding="utf-8")
    (root / ".env").write_text("API_KEY=not-for-agent", encoding="utf-8")
    (root / ".env.example").write_text("API_KEY=", encoding="utf-8")
    (root / "backend" / "credentials.py").write_text(
        'API_KEY = "' + fake_secret + '"\n',
        encoding="utf-8",
    )
    (root / "node_modules").mkdir()
    (root / "node_modules" / "package.js").write_text("secret", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "dump.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(workspace, "PROJECT_ROOT", root)

    files = workspace.list_source_files()

    assert files == [("backend/main.py", len("print('safe')"))]
    assert workspace.read_source_file("backend/main.py")[1] == "print('safe')"


@pytest.mark.parametrize(
    "file_path",
    [
        ".env",
        ".env.example",
        "data/dump.json",
        "DATA/dump.json",
        "node_modules/package.js",
        "../outside.py",
        "backend/../backend/main.py",
        "backend\\main.py",
        ".hidden/source.py",
    ],
)
def test_workspace_rejects_sensitive_or_out_of_scope_paths(tmp_path, monkeypatch, file_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".hidden").mkdir()
    for path in (".env", ".env.example", "data/dump.json", "node_modules/package.js", ".hidden/source.py"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("text", encoding="utf-8")
    monkeypatch.setattr(workspace, "PROJECT_ROOT", tmp_path)

    with pytest.raises(HTTPException):
        workspace.resolve_source_file(file_path)


def test_workspace_refuses_to_send_secret_like_source_to_provider(tmp_path, monkeypatch):
    fake_secret = "sk-proj-" + "abcdefghijklmnopqrstuvwxyz123456"
    secret_file = tmp_path / "config.py"
    secret_file.write_text(
        'client_key = "' + fake_secret + '"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(workspace, "PROJECT_ROOT", tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        workspace.read_source_file("config.py")
    assert "credential" in exc_info.value.detail


def test_workspace_refuses_to_send_password_literals_to_provider(tmp_path, monkeypatch):
    fake_password = "correct-horse-" + "battery-staple"
    secret_file = tmp_path / "config.py"
    secret_file.write_text('password = "' + fake_password + '"\n', encoding="utf-8")
    monkeypatch.setattr(workspace, "PROJECT_ROOT", tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        workspace.read_source_file("config.py")
    assert "credential" in exc_info.value.detail


def test_workspace_rejects_symlinked_source_file(tmp_path, monkeypatch):
    target = tmp_path / "real.py"
    target.write_text("value = 1\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation is not permitted in this environment")
    monkeypatch.setattr(workspace, "PROJECT_ROOT", tmp_path)

    with pytest.raises(HTTPException, match="symlink"):
        workspace.resolve_source_file("linked.py")
