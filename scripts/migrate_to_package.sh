#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="${1:-.}"
cd "$SITE_DIR"

echo "=== Migrating $(basename $(pwd)) to DjangoPress package ==="

# Safety: create backup branch
git checkout -b pre-package-migration 2>/dev/null || true
git checkout -

# Step 1: Remove framework app directories
echo "Removing framework apps..."
rm -rf core/ ai/ backoffice/ editor_v2/ site_assistant/ news/

# Step 2: Remove framework root templates and static (keep site overrides)
echo "Removing framework templates and static..."
rm -f templates/base.html templates/403.html templates/404.html templates/500.html
rm -rf templates/partials/ templates/core/ templates/backoffice/ templates/editor_v2/
rm -rf templates/news/ templates/site_assistant/ templates/sections/
rm -rf static/css/ static/js/ static/img/
# Remove templates/ and static/ dirs if empty
rmdir templates/ 2>/dev/null || true
rmdir static/ 2>/dev/null || true

# Step 3: Remove old config files (replaced by site_template versions)
echo "Removing old config..."
rm -f config/storage_backends.py config/asgi.py

# Step 4: Write thin config/settings.py and urls.py
PACKAGE_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
cp "$PACKAGE_DIR/site_template/config/settings.py" config/settings.py
cp "$PACKAGE_DIR/site_template/config/urls.py" config/urls.py

# Step 5: Update requirements.txt
echo "djangopress @ git+https://github.com/axpmarante/djangopress.git@v2.0.0" > requirements.txt

# Step 6: Remove files that are now in the package
rm -f VERSION gunicorn.conf.py
cp "$PACKAGE_DIR/site_template/gunicorn.conf.py" gunicorn.conf.py
cp "$PACKAGE_DIR/site_template/Procfile" Procfile
cp "$PACKAGE_DIR/site_template/manage.py" manage.py

# Step 7: Reinstall
echo "Installing djangopress package..."
source venv/bin/activate || source .venv/bin/activate
pip install -r requirements.txt

# Step 8: Run migrations (should be no-op)
echo "Running migrations..."
python manage.py migrate

# Step 9: Verify
echo "Verifying..."
python -c "import django; django.setup()" && echo "OK: Django starts" || echo "FAIL: Django won't start"

echo ""
echo "=== Migration complete ==="
echo "Review config/settings.py and restore any site-specific settings from .env"
echo "Backup branch: pre-package-migration"
