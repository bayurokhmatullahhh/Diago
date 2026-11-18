import hashlib
import os
import re
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAX_SOURCE_FILE_BYTES = 64 * 1024
MAX_PATCH_BYTES = 128 * 1024
MAX_DIFF_BYTES = 256 * 1024

ALLOWED_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "node_modules",
}
SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"""(?ix)\b(?:api[_-]?key|client[_-]?secret|password|passwd|secret|access[_-]?token|auth[_-]?token|token)\b
        \s*[:=]\s*(['"])(?!\s*(?:your|example|dummy|placeholder|changeme|change-me|test|none|null|empty)\b)
        [^'"\r\n]{12,}\1"""
    ),
)
LOCK_FILES = {
    "npm-shrinkwrap.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def resolve_source_file(file_path: str) -> Path:
    if not file_path or "\\" in file_path or ":" in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path file tidak valid")

    parts = file_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail="Path file tidak valid")
    root = PROJECT_ROOT.resolve()
    candidate = root.joinpath(*PurePosixPath(file_path).parts)
    current = root
    for part in PurePosixPath(file_path).parts:
        current = current / part
        if current.is_symlink():
            raise HTTPException(status_code=400, detail="Path symlink tidak tersedia untuk coding agent")
    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path harus berada di workspace project") from exc

    relative = Path(candidate.relative_to(PROJECT_ROOT.resolve()))
    if (
        any(part.startswith(".") or part.lower() in EXCLUDED_PARTS for part in relative.parts)
        or candidate.suffix.lower() not in ALLOWED_SUFFIXES
        or candidate.name.lower() in {".env", ".env.example"}
        or candidate.name.lower() in LOCK_FILES
        or candidate.name.lower().endswith((".lock", ".log"))
    ):
        raise HTTPException(status_code=400, detail="File ini tidak tersedia untuk coding agent")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    if candidate.stat().st_size > MAX_SOURCE_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File terlalu besar untuk ditinjau")
    return candidate


def read_source_file(file_path: str) -> tuple[str, str, str]:
    path = resolve_source_file(file_path)
    try:
        raw_content = path.read_bytes()
        content = raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File bukan UTF-8 text yang didukung") from exc

    if any(pattern.search(content) for pattern in SENSITIVE_PATTERNS):
        raise HTTPException(
            status_code=400,
            detail="File terlihat berisi credential atau private key dan tidak akan dikirim ke AI",
        )
    if len(raw_content) > MAX_SOURCE_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File terlalu besar untuk ditinjau")
    return _relative_path(path), content, hashlib.sha256(raw_content).hexdigest()


def list_source_files(limit: int = 300) -> list[tuple[str, int]]:
    files: list[tuple[str, int]] = []
    root = PROJECT_ROOT.resolve()
    for current_root, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if not name.startswith(".") and name not in EXCLUDED_PARTS
        ]
        current_path = Path(current_root)
        for filename in filenames:
            path = current_path / filename
            relative = path.relative_to(root)
            if (
                any(part.startswith(".") or part.lower() in EXCLUDED_PARTS for part in relative.parts)
                or path.suffix.lower() not in ALLOWED_SUFFIXES
                or path.name.lower() in {".env", ".env.example"} | LOCK_FILES
                or path.name.lower().endswith((".lock", ".log"))
            ):
                continue
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
                if size > MAX_SOURCE_FILE_BYTES:
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if any(pattern.search(content) for pattern in SENSITIVE_PATTERNS):
                    continue
                files.append((relative.as_posix(), size))
            except OSError:
                continue
            if len(files) >= limit:
                return sorted(files)
    return sorted(files)
