#Requires -Version 5.1
<#
.SYNOPSIS
    One-command dev environment setup. Idempotent — safe to run twice.
#>

$ErrorActionPreference = "Stop"

$TailwindVersion = "3.4.19"
$HtmxVersion = "2.0.10"
$AlpineVersion = "3.14.9"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

# --- 1. Python 3.11 -----------------------------------------------------
Write-Step "Checking for Python 3.11"
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if (-not $pyLauncher) {
    Write-Error "The 'py' launcher was not found. Install Python 3.11 from python.org and re-run."
    exit 1
}
$null = & py -3.11 --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 3.11 is not installed (checked via 'py -3.11'). This project pins 3.11 to match CI — install it and re-run."
    exit 1
}

# --- 2. Virtualenv --------------------------------------------------------
Write-Step "Creating virtualenv (.venv)"
if (-not (Test-Path ".venv")) {
    & py -3.11 -m venv .venv
} else {
    Write-Host "  .venv already exists, skipping creation"
}
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

# --- 3. Dependencies --------------------------------------------------------
Write-Step "Installing dependencies (requirements/dev.txt)"
& $VenvPython -m pip install --upgrade pip -q
& $VenvPython -m pip install -r requirements/dev.txt -q
if ($LASTEXITCODE -ne 0) { exit 1 }

# --- 4. .env ---------------------------------------------------------------
Write-Step "Setting up .env"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $secretKey = & $VenvPython -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
    (Get-Content ".env") -replace "^SECRET_KEY=.*$", "SECRET_KEY=$secretKey" | Set-Content ".env"
    Write-Host "  .env created from .env.example with a generated SECRET_KEY"
} else {
    Write-Host "  .env already exists, skipping"
}

# --- 5. Tailwind standalone CLI ---------------------------------------------
Write-Step "Fetching Tailwind standalone CLI ($TailwindVersion)"
if (-not (Test-Path "tools\tailwindcss.exe")) {
    New-Item -ItemType Directory -Force -Path "tools" | Out-Null
    $url = "https://github.com/tailwindlabs/tailwindcss/releases/download/v$TailwindVersion/tailwindcss-windows-x64.exe"
    Invoke-WebRequest -Uri $url -OutFile "tools\tailwindcss.exe"
} else {
    Write-Host "  tools\tailwindcss.exe already present, skipping download"
}

# --- 6. Vendor HTMX / Alpine (no CDN at runtime) ----------------------------
Write-Step "Vendoring HTMX $HtmxVersion / Alpine $AlpineVersion"
New-Item -ItemType Directory -Force -Path "static\vendor" | Out-Null
if (-not (Test-Path "static\vendor\htmx.min.js")) {
    Invoke-WebRequest -Uri "https://unpkg.com/htmx.org@$HtmxVersion/dist/htmx.min.js" -OutFile "static\vendor\htmx.min.js"
} else {
    Write-Host "  static\vendor\htmx.min.js already present, skipping download"
}
if (-not (Test-Path "static\vendor\alpine.min.js")) {
    Invoke-WebRequest -Uri "https://unpkg.com/alpinejs@$AlpineVersion/dist/cdn.min.js" -OutFile "static\vendor\alpine.min.js"
} else {
    Write-Host "  static\vendor\alpine.min.js already present, skipping download"
}

# --- 7. Build Tailwind CSS ---------------------------------------------------
Write-Step "Building static/css/app.css"
& "tools\tailwindcss.exe" -c tailwind.config.js -i static/css/input.css -o static/css/app.css --minify

# --- 8. Migrate ---------------------------------------------------------------
Write-Step "Running migrations"
& $VenvPython manage.py migrate --settings=config.settings.dev
if ($LASTEXITCODE -ne 0) { exit 1 }

# --- 9. Seed superuser (idempotent) -------------------------------------------
Write-Step "Seeding superuser from .env (skipped if one already exists)"
& $VenvPython manage.py shell --settings=config.settings.dev -c "from django.contrib.auth import get_user_model; import sys; sys.exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)" | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  A superuser already exists, skipping"
} else {
    & $VenvPython manage.py createsuperuser --noinput --settings=config.settings.dev
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# --- Done ---------------------------------------------------------------------
Write-Host ""
Write-Host "==> Setup complete." -ForegroundColor Green
Write-Host "    Activate the venv:  .venv\Scripts\Activate.ps1"
Write-Host "    Run the server:     python manage.py runserver"
Write-Host "    Run the tests:      pytest"
Write-Host "    Django admin:       http://localhost:8000/django-admin/"
Write-Host "    Health check:       http://localhost:8000/healthz/"
