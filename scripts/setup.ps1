# Setup Fase 1 (Windows PowerShell). Jalankan dari root project: .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
python --version
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host ".env dibuat dari .env.example" }
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
Write-Host "Setup selesai. Jalankan test: .\.venv\Scripts\python.exe -m pytest"
