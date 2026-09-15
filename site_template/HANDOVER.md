# Handover checklist

Read this before giving this site's code or repository to anyone outside the agency.
The site works online only with keys to external services; those keys are billed to
whoever owns them.

## 1. Keys in `.env` (local) and in the Railway service variables (production)

| Variable | Service | Before handover |
|---|---|---|
| `GEMINI_API_KEY` | Google AI (backoffice generation, image generation) | Rotate, or replace with the new owner's key |
| `UNSPLASH_ACCESS_KEY` | Unsplash search | Rotate, or replace |
| `GS_BUCKET_NAME`, `GS_PROJECT_ID`, `GCS_CREDENTIALS_JSON` | Google Cloud Storage (media) | Move the `gcs_folder` to a bucket the new owner controls, then revoke the service account |
| `MAILGUN_API_KEY`, `MAILGUN_API_URL`, `DEFAULT_FROM_EMAIL` | Mailgun (forms) | Replace with the new owner's domain and key |
| `ANTHROPIC_API_KEY` | Anthropic (backoffice assistant, if enabled) | Rotate, or remove |
| `OPENAI_API_KEY` | Should not be here: mockups use the manager's key | Remove if present |
| `SECRET_KEY` | Django | Generate a new one for the new owner |

## 2. Users

- Remove or reset the agency accounts (`pwdsuperadmin`, `pwd`) in the backoffice.
- Hand over a fresh superuser to the new owner.

## 3. Git history

`.env` is git-ignored in sites created after 2026-09-15. For older sites check:

```bash
git log --all --oneline -- .env | head
git ls-files | grep -E '^\.env$|^\.venv/' | head
```

If either prints anything, the history contains secrets: rotate every key above regardless
of what you remove from the working tree.

## 4. Third-party accounts referenced by the site

Reservations, menu services, analytics, maps: confirm which accounts stay with the client
and which were the agency's. The `## Integrations` section of the briefing lists them.
