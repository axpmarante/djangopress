#!/bin/bash
set -e
DB_PATH="/app/db.sqlite3"
LITESTREAM_CONFIG="/app/litestream.yml"
GCS_CREDS_FILE="/tmp/gcs-credentials.json"

if [ -n "$GCS_CREDENTIALS_JSON" ]; then
    echo "$GCS_CREDENTIALS_JSON" > "$GCS_CREDS_FILE"
    export GOOGLE_APPLICATION_CREDENTIALS="$GCS_CREDS_FILE"
    echo "[entrypoint] GCS credentials written to $GCS_CREDS_FILE"
else
    echo "[entrypoint] WARNING: GCS_CREDENTIALS_JSON not set"
fi

BUCKET="${GCS_BUCKET_NAME:-corporate-django-sites-media}"
REPLICA_PATH="${LITESTREAM_REPLICA_PATH:-__SITE_SLUG__/db/prod/}"

cat > "$LITESTREAM_CONFIG" <<YAML
dbs:
  - path: ${DB_PATH}
    replicas:
      - type: gcs
        bucket: ${BUCKET}
        path: ${REPLICA_PATH}
        sync-interval: 1s
YAML
echo "[entrypoint] Litestream config written (bucket=$BUCKET path=$REPLICA_PATH)"

echo "[entrypoint] Attempting database restore from GCS..."
if [ ! -f "$DB_PATH" ]; then
    if litestream restore -o "$DB_PATH" "gcs://${BUCKET}/${REPLICA_PATH}" 2>/dev/null; then
        echo "[entrypoint] Database restored from GCS"
    else
        echo "[entrypoint] No existing replica found — starting fresh"
    fi
else
    echo "[entrypoint] Database already exists — skipping restore"
fi

sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;" 2>/dev/null || true
echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput
echo "[entrypoint] Starting Litestream replication + gunicorn..."
exec litestream replicate -config "$LITESTREAM_CONFIG" -exec "gunicorn config.wsgi:application -c gunicorn.conf.py --bind 0.0.0.0:${PORT:-8000}"
