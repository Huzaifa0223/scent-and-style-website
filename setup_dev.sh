#!/usr/bin/env bash
# One-command dev environment setup. Idempotent — safe to run twice.
set -euo pipefail

TAILWIND_VERSION="3.4.19"
HTMX_VERSION="2.0.10"
ALPINE_VERSION="3.14.9"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

step() { echo; echo "==> $1"; }

# --- 1. Python 3.11 ----------------------------------------------------------
step "Checking for Python 3.11"
if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
elif python3 --version 2>&1 | grep -q "3\.11\."; then
    PYTHON_BIN="python3"
else
    echo "Python 3.11 was not found (checked 'python3.11' and 'python3'). This project pins 3.11 to match CI — install it and re-run." >&2
    exit 1
fi

# --- 2. Virtualenv ------------------------------------------------------------
step "Creating virtualenv (.venv)"
if [ ! -d ".venv" ]; then
    "$PYTHON_BIN" -m venv .venv
else
    echo "  .venv already exists, skipping creation"
fi
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

# --- 3. Dependencies -----------------------------------------------------------
step "Installing dependencies (requirements/dev.txt)"
"$VENV_PYTHON" -m pip install --upgrade pip -q
"$VENV_PYTHON" -m pip install -r requirements/dev.txt -q

# --- 4. .env ---------------------------------------------------------------------
step "Setting up .env"
if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    SECRET_KEY="$("$VENV_PYTHON" -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
    sed -i.bak "s/^SECRET_KEY=.*$/SECRET_KEY=${SECRET_KEY}/" ".env" && rm -f ".env.bak"
    echo "  .env created from .env.example with a generated SECRET_KEY"
else
    echo "  .env already exists, skipping"
fi

# --- 5. Tailwind standalone CLI ---------------------------------------------------
step "Fetching Tailwind standalone CLI ($TAILWIND_VERSION)"
mkdir -p tools
if [ ! -f "tools/tailwindcss" ]; then
    curl -sL -o tools/tailwindcss \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-x64"
    chmod +x tools/tailwindcss
else
    echo "  tools/tailwindcss already present, skipping download"
fi

# --- 6. Vendor HTMX / Alpine (no CDN at runtime) ------------------------------------
step "Vendoring HTMX $HTMX_VERSION / Alpine $ALPINE_VERSION"
mkdir -p static/vendor
if [ ! -f "static/vendor/htmx.min.js" ]; then
    curl -sL -o static/vendor/htmx.min.js "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js"
else
    echo "  static/vendor/htmx.min.js already present, skipping download"
fi
if [ ! -f "static/vendor/alpine.min.js" ]; then
    curl -sL -o static/vendor/alpine.min.js "https://unpkg.com/alpinejs@${ALPINE_VERSION}/dist/cdn.min.js"
else
    echo "  static/vendor/alpine.min.js already present, skipping download"
fi

# --- 7. Build Tailwind CSS -----------------------------------------------------------
step "Building static/css/app.css"
./tools/tailwindcss -c tailwind.config.js -i static/css/input.css -o static/css/app.css --minify

# --- 8. Migrate ------------------------------------------------------------------------
step "Running migrations"
"$VENV_PYTHON" manage.py migrate --settings=config.settings.dev

# --- 9. Seed superuser (idempotent) -----------------------------------------------------
step "Seeding superuser from .env (skipped if one already exists)"
if "$VENV_PYTHON" manage.py shell --settings=config.settings.dev -c \
    "from django.contrib.auth import get_user_model; import sys; sys.exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)" \
    >/dev/null 2>&1; then
    echo "  A superuser already exists, skipping"
else
    "$VENV_PYTHON" manage.py createsuperuser --noinput --settings=config.settings.dev
fi

# --- Done ---------------------------------------------------------------------------------
echo
echo "==> Setup complete."
echo "    Activate the venv:  source .venv/bin/activate"
echo "    Run the server:     python manage.py runserver"
echo "    Run the tests:      pytest"
echo "    Django admin:       http://localhost:8000/django-admin/"
echo "    Health check:       http://localhost:8000/healthz/"
