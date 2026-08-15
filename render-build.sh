#!/usr/bin/env bash
# Render build step for the web service (render.yaml -> buildCommand).
#
# Tailwind is fetched and run here rather than committed: static/css/app.css
# is a build artefact and is gitignored, so without this the deployed site
# would ship no stylesheet at all. The version matches setup_dev.sh,
# setup_dev.ps1 and .github/workflows/ci.yml — four places now, which is
# three too many; consolidating them is recorded in TODO.md.
set -o errexit
set -o nounset
set -o pipefail

TAILWIND_VERSION="3.4.19"

echo "==> Installing Python dependencies"
pip install -r requirements/prod.txt

echo "==> Fetching Tailwind standalone CLI (${TAILWIND_VERSION})"
mkdir -p tools
if [ ! -x tools/tailwindcss ]; then
    curl -sL -o tools/tailwindcss \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-x64"
    chmod +x tools/tailwindcss
fi

echo "==> Building CSS bundle"
./tools/tailwindcss -c tailwind.config.js -i static/css/input.css -o static/css/app.css --minify

echo "==> Collecting static files"
# Uploads to R2 when SERVE_STATIC_FROM_R2=True (config/settings/prod.py),
# since nothing on a managed platform serves STATIC_ROOT off disk.
python manage.py collectstatic --noinput

echo "==> Build complete"
