# Sentry Setup Guide

The codebase is pre-configured for Sentry. You just need to create a project on Sentry and set the DSN environment variable.

## Steps

### 1. Create a Sentry account and project

1. Go to [sentry.io](https://sentry.io) and sign up (free tier covers a single developer project).
2. Click **Create Project**.
3. Select **Django** as the platform.
4. Name the project (e.g., `architextual`).
5. Click **Create Project** — Sentry will show you a DSN string.

### 2. Copy your DSN

The DSN looks like:

```
https://examplePublicKey@o0.ingest.sentry.io/0
```

You only need this one value.

### 3. Set the environment variable

**Local development** — add to your `.env` file:

```ini
SENTRY_DSN=https://your-key@o0.ingest.sentry.io/0
SENTRY_ENVIRONMENT=development
```

**Railway (production)** — add these as environment variables in your Railway service settings:

```
SENTRY_DSN=https://your-key@o0.ingest.sentry.io/0
SENTRY_ENVIRONMENT=production
```

### 4. Verify it works

Deploy or restart the app, then trigger a test error:

```bash
uv run python manage.py shell -c "
import sentry_sdk
sentry_sdk.capture_message('Sentry test from Architextual')
print('Sent test event — check your Sentry dashboard.')
"
```

The event should appear in your Sentry dashboard within a few seconds.

### 5. Optional: Tune settings

The integration in `settings.py` is configured with:

| Setting | Value | Purpose |
|---------|-------|---------|
| `traces_sample_rate` | `0.1` | Capture 10% of requests for performance tracing |
| `profiles_sample_rate` | `0.1` | Profile 10% of traced requests |
| `send_default_pii` | `False` | Do not send user emails/IPs to Sentry |

To increase tracing coverage (costs more quota), raise `traces_sample_rate` toward `1.0`. For a low-traffic personal blog, `1.0` is fine and stays within the free tier.

To disable Sentry entirely, remove the `SENTRY_DSN` environment variable — the integration is skipped when the variable is absent.
