import ast
import logging
import os
import re
from pathlib import Path

from app.agent.workspace import (
    ALLOWED_SUFFIXES,
    EXCLUDED_PARTS,
    LOCK_FILES,
    MAX_SOURCE_FILE_BYTES,
    PROJECT_ROOT,
    SENSITIVE_PATTERNS,
)
from app.schemas.agent import SecurityFinding, SecurityScanResponse

logger = logging.getLogger("app.agent.security_scan")

MAX_SCAN_FILES = 1000
MAX_SCAN_TOTAL_BYTES = 20 * 1024 * 1024
MAX_FINDINGS = 500
CODE_SUFFIXES = ALLOWED_SUFFIXES - {".md", ".txt"}
SECRET_PATTERNS = SENSITIVE_PATTERNS + (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
SQL_STATEMENT = re.compile(r"(?i)\b(?:SELECT|INSERT|UPDATE|DELETE|REPLACE)\b")
RULES: tuple[
    tuple[str, str, str, re.Pattern[str], str],
    ...,
] = (
    (
        "hardcoded-credential",
        "high",
        "Kemungkinan credential tertanam di source",
        re.compile(
            r"""(?ix)\b(?:api[_-]?key|client[_-]?secret|password|passwd|secret|access[_-]?token|auth[_-]?token|token)\b
            \s*[:=]\s*(['"])(?!\s*(?:your|example|dummy|placeholder|changeme|change-me|test|none|null|empty)\b)
            [^'"\r\n]{12,}\1"""
        ),
        "Pindahkan credential ke environment/secret manager dan rotasi nilainya bila nyata.",
    ),
    (
        "tls-verification-disabled",
        "high",
        "Verifikasi TLS tampak dinonaktifkan",
        re.compile(r"(?i)\bverify\s*=\s*False\b|_create_unverified_context\s*\(|\bCERT_NONE\b"),
        "Aktifkan verifikasi sertifikat TLS dan jangan menonaktifkannya di production.",
    ),
    (
        "dynamic-code-execution",
        "medium",
        "Eksekusi kode dinamis terdeteksi",
        re.compile(r"\b(?:eval|exec)\s*\("),
        "Hindari eval/exec untuk input dinamis; gunakan parser dan operasi yang dibatasi.",
    ),
    (
        "wildcard-cors",
        "medium",
        "Konfigurasi CORS wildcard terdeteksi",
        re.compile(r"""(?is)allow_origins\s*=\s*\[[^\]]{0,500}["']\*["']"""),
        "Batasi CORS ke origin frontend yang dipercaya dan gunakan allowlist eksplisit.",
    ),
    (
        "dangerous-html-injection",
        "medium",
        "dangerouslySetInnerHTML terdeteksi",
        re.compile(r"\bdangerouslySetInnerHTML\s*="),
        "Sanitasi konten HTML tak tepercaya sebelum render atau hindari HTML mentah.",
    ),
)

LIMITATIONS = [
    "Pemeriksaan statis dan AST bersifat heuristik; false positive dan false negative mungkin terjadi.",
    "File environment, database, dependency/build, hidden, dan lockfile tidak dipindai.",
    "Kerentanan dependency dan website live tidak diperiksa.",
    "Pemindaian lokal ini tidak membuktikan aplikasi aman dan bukan pengganti security review.",
    "Tidak ada kode project yang dijalankan, jaringan yang diakses, atau source yang dikirim ke AI.",
]


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _contains_dynamic_value(node: ast.expr) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return not (
            isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str)
            and isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, str)
        )
    return False


def _python_findings(content: str, file_path: str) -> list[tuple[str, str, str, int, str]]:
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        logger.warning(
            "Could not parse Python security scan file %s at line %s",
            file_path,
            exc.lineno,
        )
        return []

    findings: list[tuple[str, str, str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            allow_origins = any(
                (isinstance(target, ast.Name) and target.id == "allow_origins")
                or (isinstance(target, ast.Attribute) and target.attr == "allow_origins")
                for target in targets
            )
            value = node.value
            if (
                allow_origins
                and isinstance(value, (ast.List, ast.Tuple, ast.Set))
                and any(
                    isinstance(item, ast.Constant) and item.value == "*"
                    for item in value.elts
                )
            ):
                findings.append((
                    "wildcard-cors",
                    "medium",
                    "Konfigurasi CORS wildcard terdeteksi",
                    node.lineno,
                    "Batasi CORS ke origin frontend yang dipercaya dan gunakan allowlist eksplisit.",
                ))
        if isinstance(node, ast.Attribute) and node.attr == "CERT_NONE":
            findings.append((
                "tls-verification-disabled",
                "high",
                "Verifikasi TLS tampak dinonaktifkan",
                node.lineno,
                "Aktifkan verifikasi sertifikat TLS dan jangan menonaktifkannya di production.",
            ))
        if not isinstance(node, ast.Call):
            continue

        name = _call_name(node.func)
        verify_disabled = any(
            keyword.arg == "verify"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in node.keywords
        )
        if verify_disabled or name == "ssl._create_unverified_context":
            findings.append((
                "tls-verification-disabled",
                "high",
                "Verifikasi TLS tampak dinonaktifkan",
                node.lineno,
                "Aktifkan verifikasi sertifikat TLS dan jangan menonaktifkannya di production.",
            ))
        elif name in {"eval", "exec"}:
            findings.append((
                "dynamic-code-execution",
                "medium",
                "Eksekusi kode dinamis terdeteksi",
                node.lineno,
                "Hindari eval/exec untuk input dinamis; gunakan parser dan operasi yang dibatasi.",
            ))
        elif name in {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
        } and any(
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        ):
            findings.append((
                "shell-command-execution",
                "high",
                "Pemanggilan proses dengan shell=True",
                node.lineno,
                "Hindari shell=True; gunakan daftar argumen tetap dan validasi input dengan ketat.",
            ))
        elif name in {"pickle.load", "pickle.loads", "dill.load", "dill.loads", "joblib.load"}:
            findings.append((
                "unsafe-deserialization",
                "high",
                "Deserialisasi objek berisiko",
                node.lineno,
                "Jangan deserialisasi data tidak tepercaya dengan pickle/dill/joblib; gunakan format data aman.",
            ))
        elif name == "yaml.load":
            loader = next((keyword.value for keyword in node.keywords if keyword.arg == "Loader"), None)
            safe_loader = (
                isinstance(loader, ast.Name)
                and loader.id in {"SafeLoader", "CSafeLoader"}
            ) or (
                isinstance(loader, ast.Attribute)
                and loader.attr in {"SafeLoader", "CSafeLoader"}
            )
            if not safe_loader:
                findings.append((
                    "unsafe-yaml-load",
                    "high",
                    "yaml.load tanpa SafeLoader",
                    node.lineno,
                    "Gunakan yaml.safe_load atau SafeLoader untuk memproses YAML yang tidak tepercaya.",
                ))
        elif (
            name.endswith(".execute")
            and node.args
            and _contains_dynamic_value(node.args[0])
            and any(
                isinstance(part, ast.Constant)
                and isinstance(part.value, str)
                and SQL_STATEMENT.search(part.value)
                for part in ast.walk(node.args[0])
            )
        ):
            findings.append((
                "dynamic-sql",
                "high",
                "Query SQL dirangkai secara dinamis",
                node.lineno,
                "Gunakan query berparameter; jangan sisipkan nilai dinamis ke string SQL.",
            ))
    return findings


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def run_local_security_scan(root: Path = PROJECT_ROOT) -> SecurityScanResponse:
    scan_root = root.resolve()
    scanned_files = 0
    skipped_files = 0
    total_bytes = 0
    findings: list[SecurityFinding] = []
    seen: set[tuple[str, str, int]] = set()

    for current_root, directories, filenames in os.walk(scan_root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if not name.startswith(".") and name.lower() not in EXCLUDED_PARTS
        )
        current_path = Path(current_root)
        for filename in sorted(filenames):
            path = current_path / filename
            relative = path.relative_to(scan_root)
            if (
                any(part.startswith(".") or part.lower() in EXCLUDED_PARTS for part in relative.parts)
                or path.suffix.lower() not in ALLOWED_SUFFIXES
                or path.name.lower() in {".env", ".env.example"} | LOCK_FILES
                or path.name.lower().endswith((".lock", ".log"))
                or path.is_symlink()
            ):
                skipped_files += 1
                continue
            try:
                size = path.stat().st_size
                if size > MAX_SOURCE_FILE_BYTES or total_bytes + size > MAX_SCAN_TOTAL_BYTES:
                    skipped_files += 1
                    continue
                raw_content = path.read_bytes()
                content = raw_content.decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                skipped_files += 1
                logger.warning(
                    "Could not read security scan file %s (%s)",
                    _relative_path(scan_root, path),
                    type(exc).__name__,
                )
                continue

            total_bytes += len(raw_content)
            scanned_files += 1
            path_text = _relative_path(scan_root, path)

            for pattern in SECRET_PATTERNS:
                for match in pattern.finditer(content):
                    line_number = content.count("\n", 0, match.start()) + 1
                    key = ("hardcoded-credential", path_text, line_number)
                    if key not in seen:
                        seen.add(key)
                        findings.append(
                            SecurityFinding(
                                rule_id="hardcoded-credential",
                                severity="high",
                                title="Kemungkinan credential tertanam di source",
                                file_path=path_text,
                                line=line_number,
                                description="Pola yang mirip secret/token terdeteksi; nilai tidak ditampilkan.",
                                recommendation="Pastikan ini bukan secret aktif. Pindahkan nilai rahasia ke secret manager dan rotasi bila nyata.",
                                confidence="medium",
                            )
                        )
            if path.suffix.lower() in CODE_SUFFIXES:
                python_findings = (
                    _python_findings(content, path_text)
                    if path.suffix.lower() == ".py"
                    else []
                )
                for rule_id, severity, title, line_number, recommendation in python_findings:
                    key = (rule_id, path_text, line_number)
                    if key not in seen:
                        seen.add(key)
                        findings.append(
                            SecurityFinding(
                                rule_id=rule_id,
                                severity=severity,
                                title=title,
                                file_path=path_text,
                                line=line_number,
                                description="Pola berisiko terdeteksi; tinjau konteks sebelum mengambil tindakan.",
                                recommendation=recommendation,
                                confidence="medium",
                            )
                        )

                for rule_id, severity, title, pattern, recommendation in RULES:
                    if path.suffix.lower() == ".py" and rule_id in {
                        "dynamic-code-execution",
                        "tls-verification-disabled",
                        "wildcard-cors",
                    }:
                        continue
                    for match in pattern.finditer(content):
                        line_number = content.count("\n", 0, match.start()) + 1
                        key = (rule_id, path_text, line_number)
                        if key in seen:
                            continue
                        seen.add(key)
                        findings.append(
                            SecurityFinding(
                                rule_id=rule_id,
                                severity=severity,
                                title=title,
                                file_path=path_text,
                                line=line_number,
                                description="Pola berisiko terdeteksi; tinjau konteks sebelum mengambil tindakan.",
                                recommendation=recommendation,
                                confidence="medium",
                            )
                        )
                        if len(findings) >= MAX_FINDINGS:
                            break
                    if len(findings) >= MAX_FINDINGS:
                        break

            if len(findings) >= MAX_FINDINGS or scanned_files >= MAX_SCAN_FILES:
                break
        if len(findings) >= MAX_FINDINGS or scanned_files >= MAX_SCAN_FILES:
            break

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(
        key=lambda finding: (
            severity_order[finding.severity],
            finding.file_path,
            finding.line,
            finding.rule_id,
        )
    )
    return SecurityScanResponse(
        scanned_files=scanned_files,
        skipped_files=skipped_files,
        findings=findings,
        high_count=sum(finding.severity == "high" for finding in findings),
        medium_count=sum(finding.severity == "medium" for finding in findings),
        low_count=sum(finding.severity == "low" for finding in findings),
        limitations=LIMITATIONS,
    )
