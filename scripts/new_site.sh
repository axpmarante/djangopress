#!/usr/bin/env bash
#
# Create a new DjangoPress site from the site_template scaffold.
#
# Usage:
#   ./scripts/new_site.sh <project-name> [briefing-file]
#
# Examples:
#   ./scripts/new_site.sh windmill-restaurant
#   ./scripts/new_site.sh windmill-restaurant briefings/example-restaurant.md
#
# This script:
#   1. Copies site_template/ into ../<project-name>/
#   2. Copies API keys from the current project's .env (reuses provider keys)
#   3. Generates a unique SECRET_KEY
#   4. Creates a virtual environment and installs dependencies (pulls djangopress from GitHub)
#   5. Runs migrations
#   6. Optionally copies a briefing file into the new project
#   7. Initializes a fresh git repo

set -euo pipefail

# --- Arguments ---
PROJECT_NAME="${1:-}"
BRIEFING_FILE="${2:-}"

if [ -z "$PROJECT_NAME" ]; then
    echo "Usage: ./scripts/new_site.sh <project-name> [briefing-file]"
    echo ""
    echo "Examples:"
    echo "  ./scripts/new_site.sh windmill-restaurant"
    echo "  ./scripts/new_site.sh windmill-restaurant briefings/example-restaurant.md"
    exit 1
fi

# --- Paths ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATE_DIR="$SOURCE_DIR/site_template"
PARENT_DIR="$(dirname "$SOURCE_DIR")"
TARGET_DIR="$PARENT_DIR/$PROJECT_NAME"

echo "=== DjangoPress: New Site Setup ==="
echo ""
echo "  Template: $TEMPLATE_DIR"
echo "  Target:   $TARGET_DIR"
echo ""

# --- Check template exists ---
if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "ERROR: site_template directory not found: $TEMPLATE_DIR"
    exit 1
fi

# --- Check target doesn't exist ---
if [ -d "$TARGET_DIR" ]; then
    echo "ERROR: Directory already exists: $TARGET_DIR"
    echo "  Remove it first or choose a different project name."
    exit 1
fi

# --- Check briefing file exists (if provided) ---
if [ -n "$BRIEFING_FILE" ] && [ ! -f "$BRIEFING_FILE" ]; then
    echo "ERROR: Briefing file not found: $BRIEFING_FILE"
    exit 1
fi

# --- Step 1: Copy site_template ---
echo "--- Step 1: Copying site template ---"
cp -R "$TEMPLATE_DIR" "$TARGET_DIR"
echo "  Template copied"

cd "$TARGET_DIR"

# --- Step 2: Configure .env ---
echo ""
echo "--- Step 2: Configuring .env ---"

if [ -f "$SOURCE_DIR/.env" ]; then
    echo "  Copying API keys from source project..."

    # Start with the example file
    cp .env.example .env

    # Extract API keys from source .env and apply them
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
        # Only copy specific keys (API keys, not project-specific settings)
        case "$key" in
            GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|UNSPLASH_ACCESS_KEY|\
            GS_BUCKET_NAME|GS_PROJECT_ID|\
            MAILGUN_API_KEY|MAILGUN_API_URL|DEFAULT_FROM_EMAIL)
                # Replace the key in the new .env
                if grep -q "^${key}=" .env 2>/dev/null; then
                    sed -i.bak "s|^${key}=.*|${key}=${value}|" .env
                else
                    echo "${key}=${value}" >> .env
                fi
                echo "  Copied: $key"
                ;;
        esac
    done < "$SOURCE_DIR/.env"
    rm -f .env.bak

    # GCS_CREDENTIALS_JSON needs special handling — it contains characters
    # that break sed (=, /, +, newlines in base64). Copy the whole line directly.
    if grep -q "^GCS_CREDENTIALS_JSON=" "$SOURCE_DIR/.env" 2>/dev/null; then
        # Remove any existing entry first
        grep -v "^GCS_CREDENTIALS_JSON=" .env > .env.tmp && mv .env.tmp .env
        # Copy the line verbatim from source
        grep "^GCS_CREDENTIALS_JSON=" "$SOURCE_DIR/.env" >> .env
        echo "  Copied: GCS_CREDENTIALS_JSON"
    fi
else
    echo "  No source .env found. Copying from .env.example..."
    cp .env.example .env
fi

# Generate a unique SECRET_KEY
echo "  Generating SECRET_KEY..."
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
rm -f .env.bak

# Set environment to development
sed -i.bak "s|^ENVIRONMENT=.*|ENVIRONMENT=development|" .env
rm -f .env.bak

echo "  .env configured"

# --- Step 3: Virtual environment and dependencies ---
echo ""
echo "--- Step 3: Installing dependencies ---"

python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
# Re-install djangopress from the local source to get the latest version
# (requirements.txt pins a git tag for Railway deploys, but locally we want current)
pip install -q "$SOURCE_DIR"
echo "  Dependencies installed (djangopress from local source: $SOURCE_DIR)"

# --- Step 4: Database ---
echo ""
echo "--- Step 4: Running migrations ---"

python manage.py migrate --verbosity 0
echo "  Database ready"

# --- Step 4b: Sync Claude Code skills ---
echo ""
echo "--- Step 4b: Syncing Claude Code skills ---"
python manage.py sync_skills --clean
echo "  Skills synced"

# --- Step 5: Copy briefing file ---
if [ -n "$BRIEFING_FILE" ]; then
    echo ""
    echo "--- Step 5: Copying briefing file ---"
    mkdir -p briefings
    cp "$BRIEFING_FILE" briefings/
    BRIEFING_NAME=$(basename "$BRIEFING_FILE")
    echo "  Copied to: briefings/$BRIEFING_NAME"
fi

# --- Step 6: Initialize git repo ---
echo ""
echo "--- Step 6: Initializing git repository ---"
git init -q
git add -A
git commit -q -m "Initial commit from DjangoPress site template"
echo "  Git repository initialized"

# --- Done ---
echo ""
echo "============================================"
echo "  Project ready: $TARGET_DIR"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "  cd $TARGET_DIR"
echo "  source venv/bin/activate"
echo ""

if [ -n "$BRIEFING_FILE" ]; then
    BRIEFING_NAME=$(basename "$BRIEFING_FILE")
    echo "  # Interactive (recommended — Claude Code reviews quality):"
    echo "  claude /generate-site briefings/$BRIEFING_NAME"
    echo ""
    echo "  # Or non-interactive:"
    echo "  python manage.py generate_site briefings/$BRIEFING_NAME"
else
    echo "  # Create a briefing file first:"
    echo "  cp briefings/TEMPLATE.md briefings/my-site.md"
    echo "  # Edit it with your business details, then:"
    echo "  claude /generate-site briefings/my-site.md"
fi

echo ""
echo "  # Or set up manually:"
echo "  python manage.py createsuperuser"
echo "  python manage.py runserver 8000"
echo "  # Visit http://localhost:8000/backoffice/settings/"
