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

echo "1. Flushing the local database to the dev replica..."
if pkill -f "litestream replicate" 2>/dev/null; then
    echo "   Stopped the running Litestream (pending WAL frames flushed)."
else
    # No replicator running: push the current db.sqlite3 with a one-shot replicate,
    # otherwise local edits made since the last replication never reach prod.
    LS_BIN="${LITESTREAM_BIN:-$HOME/bin/litestream}"; command -v litestream >/dev/null 2>&1 && LS_BIN=litestream
    sqlite3 db.sqlite3 "PRAGMA journal_mode=WAL;" >/dev/null 2>&1 || true
    "$LS_BIN" replicate -config litestream.yml >/dev/null 2>&1 &
    sleep 12
    pkill -f "litestream replicate" 2>/dev/null
    echo "   One-shot replicate done."
fi
sleep 2

echo "2. Checking dev replica..."
if ! gcloud storage ls "$BUCKET/$DEV_PATH/" > /dev/null 2>&1; then
    echo "ERROR: No dev replica found at $BUCKET/$DEV_PATH/"
    echo "Run Litestream locally first to create the replica."
    exit 1
fi

# Each `litestream replicate` invocation creates a fresh generation (no
# persistent local state between runs), so dev accumulates them. Litestream's
# restore picks whichever it considers "latest" — which may not be the most
# recent — so prune to a single generation before syncing.
echo "3. Pruning stale dev generations (keeping latest only)..."
LATEST_GEN=""
LATEST_TS=""
for gen_path in $(gcloud storage ls "$BUCKET/$DEV_PATH/generations/" 2>/dev/null); do
    gen=$(basename "${gen_path%/}")
    ts=$(gcloud storage ls -l "$gen_path**" 2>/dev/null \
        | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z' \
        | sort | tail -1)
    if [ -n "$ts" ] && { [ -z "$LATEST_TS" ] || [ "$ts" \> "$LATEST_TS" ]; }; then
        LATEST_TS="$ts"
        LATEST_GEN="$gen"
    fi
done

if [ -z "$LATEST_GEN" ]; then
    echo "ERROR: No generations found in dev"
    exit 1
fi
echo "   Latest dev generation: $LATEST_GEN ($LATEST_TS)"

PRUNED=0
for gen_path in $(gcloud storage ls "$BUCKET/$DEV_PATH/generations/" 2>/dev/null); do
    gen=$(basename "${gen_path%/}")
    if [ "$gen" != "$LATEST_GEN" ]; then
        echo "   Removing stale dev generation: $gen"
        gcloud storage rm -r "$gen_path" --quiet
        PRUNED=$((PRUNED + 1))
    fi
done
echo "   Pruned $PRUNED stale generation(s) from dev."

echo "4. Backing up current prod to $PROD_PATH-backup-$TIMESTAMP/..."
if gcloud storage ls "$BUCKET/$PROD_PATH/" > /dev/null 2>&1; then
    gcloud storage cp -r "$BUCKET/$PROD_PATH" "$BUCKET/$PROD_PATH-backup-$TIMESTAMP"
    echo "   Backup saved."
else
    echo "   No existing prod replica — skipping backup."
fi

echo "5. Copying dev replica to prod..."
gcloud storage rsync -r --delete-unmatched-destination-objects "$BUCKET/$DEV_PATH/" "$BUCKET/$PROD_PATH/"
echo "   Done."

echo ""
echo "=== Sync complete ==="
echo ""
echo "Next steps:"
echo "  1. Deploy to Railway: railway up -d"
echo "  2. Verify the site works"
echo "  3. If something went wrong, restore from backup:"
echo "     gcloud storage rsync -r --delete-unmatched-destination-objects \\"
echo "       $BUCKET/$PROD_PATH-backup-$TIMESTAMP/ $BUCKET/$PROD_PATH/"
echo "     railway up -d"
