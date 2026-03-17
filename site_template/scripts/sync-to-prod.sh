#!/bin/bash
set -e
SITE_SLUG=$(basename "$(pwd)")
BUCKET="gs://corporate-django-sites-media"
DEV_PATH="$SITE_SLUG/db/dev"
PROD_PATH="$SITE_SLUG/db/prod"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "=== Sync Dev → Prod ($SITE_SLUG) ==="
echo ""

if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS not set"
    echo "Run: export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json"
    exit 1
fi

echo "1. Stopping local Litestream (flushing pending WAL frames)..."
pkill -f "litestream replicate" 2>/dev/null && echo "   Stopped." || echo "   Not running."
sleep 2

echo "2. Checking dev replica..."
if ! gcloud storage ls "$BUCKET/$DEV_PATH/" > /dev/null 2>&1; then
    echo "ERROR: No dev replica found at $BUCKET/$DEV_PATH/"
    echo "Run Litestream locally first to create the replica."
    exit 1
fi

echo "3. Backing up current prod..."
if gcloud storage ls "$BUCKET/$PROD_PATH/" > /dev/null 2>&1; then
    gcloud storage cp -r "$BUCKET/$PROD_PATH" "$BUCKET/$PROD_PATH-backup-$TIMESTAMP"
    echo "   Backup saved."
else
    echo "   No existing prod replica — skipping backup."
fi

echo "4. Copying dev replica to prod..."
gcloud storage rsync -r --delete-unmatched-destination-objects "$BUCKET/$DEV_PATH/" "$BUCKET/$PROD_PATH/"
echo "   Done."

echo ""
echo "=== Sync complete ==="
echo ""
echo "Next steps:"
echo "  1. Deploy to Railway: railway up -d"
echo "  2. Verify the site works"
