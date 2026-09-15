#!/bin/bash
set -e
SITE_SLUG=$(basename "$(pwd)")
DB_PATH="db.sqlite3"
BUCKET="gs://corporate-django-sites-media"
PROD_PATH="$SITE_SLUG/db/prod"

LITESTREAM="${LITESTREAM:-$(command -v litestream 2>/dev/null || echo "$HOME/bin/litestream")}"

echo "=== Pull Prod → Dev ($SITE_SLUG) ==="
echo ""

if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS not set"
    echo "Run: export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json"
    exit 1
fi

if [ ! -x "$LITESTREAM" ]; then
    echo "ERROR: litestream binary not found (tried PATH and ~/bin/litestream)"
    echo "Install with: curl -L https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-darwin-arm64.zip -o /tmp/litestream.zip && unzip -o /tmp/litestream.zip -d /tmp/ && mkdir -p ~/bin && mv /tmp/litestream ~/bin/litestream && chmod +x ~/bin/litestream"
    exit 1
fi

echo "1. Checking prod replica..."
if ! gcloud storage ls "$BUCKET/$PROD_PATH/" > /dev/null 2>&1; then
    echo "ERROR: No prod replica found at $BUCKET/$PROD_PATH/"
    exit 1
fi

echo "2. Stopping local Litestream..."
pkill -f "litestream replicate" 2>/dev/null && echo "   Stopped." || echo "   Not running."
sleep 2

echo "3. Backing up local database..."
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "${DB_PATH}.bak"
    echo "   Saved to ${DB_PATH}.bak"
fi

rm -f "$DB_PATH" "${DB_PATH}-wal" "${DB_PATH}-shm"

echo "4. Restoring from prod replica..."
"$LITESTREAM" restore -o "$DB_PATH" "gcs://corporate-django-sites-media/$PROD_PATH"

sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;"

echo ""
echo "=== Pull complete ==="
echo "Local database now matches production."
echo "To remove backup: rm ${DB_PATH}.bak"
