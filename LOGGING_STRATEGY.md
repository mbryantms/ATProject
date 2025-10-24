# Logging Strategy for ATProject

**Project**: Architextual (ATProject)
**Date**: 2025-10-10
**Type**: Django 5.2.7 Blog Platform with Celery

---

## Table of Contents

- [Current State Analysis](#current-state-analysis)
- [Recommended Logging Architecture](#recommended-logging-architecture)
- [Implementation Plan](#implementation-plan)
- [Logging Levels Strategy](#logging-levels-strategy)
- [Third-Party Services & Packages](#third-party-services--packages)
- [Configuration Examples](#configuration-examples)
- [Best Practices](#best-practices)
- [Monitoring & Alerting](#monitoring--alerting)

---

## Current State Analysis

### Existing Logging Implementation

**Status**: Minimal, inconsistent logging

**Files with Logging**:
1. `engine/signals.py` - Signal handlers for post links
   - Logger: `logging.getLogger(__name__)`
   - Levels used: DEBUG, INFO, WARNING, ERROR
   - Good practices: Uses `exc_info=True` for exceptions

2. `engine/links/extractor.py` - Internal link extraction
   - Logger: `logging.getLogger(__name__)`
   - Well-implemented structured logging

3. `engine/metadata_extractor.py` - Asset metadata extraction
   - Logger: `logging.getLogger(__name__)`
   - Uses INFO and WARNING levels
   - Good diagnostic logging

4. `engine/markdown/postprocessors/sanitizer.py` - HTML sanitization
   - Logger: `logging.getLogger(__name__)`

### Gaps Identified

❌ **No centralized logging configuration** in `settings.py`
❌ **No structured logging** (JSON/structured format)
❌ **No log aggregation** or centralized storage
❌ **No performance monitoring** (request/response times)
❌ **No security logging** (authentication, access control)
❌ **No Celery task logging** integration
❌ **No database query logging** for performance
❌ **No external error tracking** (Sentry, Rollbar, etc.)
❌ **Inconsistent coverage** - most modules have no logging

---

## Recommended Logging Architecture

### Multi-Tier Logging Strategy

```
┌─────────────────────────────────────────────────────────┐
│                   Application Layer                      │
│  ┌─────────────┐  ┌──────────┐  ┌─────────────────┐    │
│  │  Django App │  │  Celery  │  │  Admin Actions  │    │
│  └──────┬──────┘  └────┬─────┘  └────────┬────────┘    │
└─────────┼───────────────┼─────────────────┼─────────────┘
          │               │                 │
          └───────────────┴─────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │   Python Logging Framework    │
          │   (Structured JSON Format)    │
          └───────────┬───────────────────┘
                      │
          ┌───────────┴───────────────┐
          │                           │
  ┌───────┴────────┐         ┌────────┴─────────┐
  │  Local Files   │         │  Cloud Service   │
  │  - Rotation    │         │  - Sentry/Rollbar│
  │  - Retention   │         │  - CloudWatch    │
  │  - Debug info  │         │  - Papertrail    │
  └────────────────┘         └──────────────────┘
```

### Core Principles

1. **Structured Logging**: JSON format for machine parsing
2. **Context-Rich**: Request ID, user ID, trace IDs
3. **Performance-Aware**: Async logging, buffering
4. **Environment-Specific**: Different configs for dev/staging/prod
5. **Secure**: No PII, credentials, or sensitive data
6. **Actionable**: Logs should enable debugging and monitoring

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

#### 1.1 Configure Django Logging

Add comprehensive logging configuration to `settings.py`:

```python
# ATProject/settings.py

import os
from pathlib import Path

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module}.{funcName}:{lineno} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'console_debug': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file_general': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/general.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/error.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/security.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'file_performance': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/performance.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'json',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        },
    },
    'loggers': {
        '': {  # Root logger
            'handlers': ['console', 'file_general', 'file_error'],
            'level': 'INFO',
        },
        'django': {
            'handlers': ['console', 'file_general'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_error', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file_security', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console_debug'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'engine': {
            'handlers': ['console', 'file_general', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file_general', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['console', 'file_general'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Ensure log directory exists
(BASE_DIR / 'logs').mkdir(exist_ok=True)
```

#### 1.2 Add Required Packages

Update `pyproject.toml`:

```toml
dependencies = [
    # ... existing dependencies ...
    "python-json-logger>=2.0.7",  # Structured JSON logging
    "django-log-request-id>=2.1.0",  # Request ID tracking
]
```

### Phase 2: Enhanced Logging (Week 2)

#### 2.1 Request Tracking Middleware

Create `engine/middleware/logging.py`:

```python
import logging
import time
import uuid
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)
performance_logger = logging.getLogger('performance')


class RequestLoggingMiddleware(MiddlewareMixin):
    """Log all requests with timing and context."""

    def process_request(self, request):
        # Generate unique request ID
        request.request_id = str(uuid.uuid4())
        request.start_time = time.time()

        # Add request ID to logging context
        logger.info(
            "Request started",
            extra={
                'request_id': request.request_id,
                'method': request.method,
                'path': request.path,
                'user': str(request.user) if request.user.is_authenticated else 'anonymous',
                'ip': self.get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            }
        )

    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time

            performance_logger.info(
                "Request completed",
                extra={
                    'request_id': getattr(request, 'request_id', 'unknown'),
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                    'duration_ms': round(duration * 1000, 2),
                    'user': str(request.user) if request.user.is_authenticated else 'anonymous',
                }
            )

        return response

    def process_exception(self, request, exception):
        logger.error(
            "Request exception",
            extra={
                'request_id': getattr(request, 'request_id', 'unknown'),
                'method': request.method,
                'path': request.path,
                'exception_type': type(exception).__name__,
                'exception_message': str(exception),
            },
            exc_info=True
        )

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
```

#### 2.2 Security Logging

Create `engine/middleware/security_logging.py`:

```python
import logging
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

security_logger = logging.getLogger('django.security')


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    security_logger.info(
        "User login successful",
        extra={
            'user': user.username,
            'user_id': user.id,
            'ip': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        }
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        security_logger.info(
            "User logout",
            extra={
                'user': user.username,
                'user_id': user.id,
            }
        )


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    security_logger.warning(
        "User login failed",
        extra={
            'username': credentials.get('username', 'unknown'),
            'ip': request.META.get('REMOTE_ADDR') if request else 'unknown',
        }
    )
```

#### 2.3 Celery Task Logging

Update `ATProject/celery.py`:

```python
import logging
from celery import Celery
from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_retry,
)

logger = logging.getLogger('celery.task')


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    logger.info(
        f"Task started: {task.name}",
        extra={
            'task_id': task_id,
            'task_name': task.name,
            'args': str(args)[:200],  # Truncate for safety
        }
    )


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, retval=None, **extra):
    logger.info(
        f"Task completed: {task.name}",
        extra={
            'task_id': task_id,
            'task_name': task.name,
        }
    )


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **extra):
    logger.error(
        f"Task failed: {sender.name}",
        extra={
            'task_id': task_id,
            'task_name': sender.name,
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
        },
        exc_info=True
    )


@task_retry.connect
def task_retry_handler(sender=None, task_id=None, reason=None, **extra):
    logger.warning(
        f"Task retry: {sender.name}",
        extra={
            'task_id': task_id,
            'task_name': sender.name,
            'reason': str(reason),
        }
    )
```

### Phase 3: External Services (Week 3-4)

#### 3.1 Error Tracking with Sentry

**Best for**: Production error tracking, performance monitoring

```bash
uv add sentry-sdk
```

```python
# ATProject/settings.py

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

if not DEBUG:
    sentry_sdk.init(
        dsn=env("SENTRY_DSN"),
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
        profiles_sample_rate=0.1,  # 10% for profiling
        environment=env("ENVIRONMENT", default="production"),
        release=env("GIT_COMMIT", default="unknown"),
        send_default_pii=False,  # Don't send PII
        before_send=before_send_sentry,  # Filter function
    )


def before_send_sentry(event, hint):
    """Filter sensitive data before sending to Sentry."""
    # Remove sensitive keys from request data
    if 'request' in event:
        if 'data' in event['request']:
            sensitive_keys = ['password', 'token', 'secret', 'api_key']
            for key in sensitive_keys:
                if key in event['request']['data']:
                    event['request']['data'][key] = '[FILTERED]'
    return event
```

---

## Logging Levels Strategy

### Level Hierarchy

```
CRITICAL (50) - System is unusable, immediate action required
   ↓
ERROR (40)    - Errors that prevent operation but don't crash the system
   ↓
WARNING (30)  - Warning messages for unusual situations
   ↓
INFO (20)     - Informational messages about normal operation
   ↓
DEBUG (10)    - Detailed diagnostic information
```

### When to Use Each Level

#### CRITICAL
**Use for**: Complete system failures requiring immediate intervention

**Examples**:
- Database connection permanently lost
- Critical external service unavailable (payment gateway down)
- Security breach detected
- Data corruption discovered

```python
logger.critical(
    "Database connection lost - all write operations failing",
    extra={'database': 'postgresql', 'retry_attempts': 3}
)
```

#### ERROR
**Use for**: Operation failures that don't crash the system but prevent functionality

**Examples**:
- Failed to process user upload
- Email sending failed
- Failed to generate asset rendition
- Failed to update search index

```python
logger.error(
    "Failed to generate asset rendition",
    extra={
        'asset_key': asset.key,
        'requested_width': width,
        'error_type': type(e).__name__,
    },
    exc_info=True
)
```

#### WARNING
**Use for**: Unexpected situations that might cause problems

**Examples**:
- API rate limit approaching
- Deprecated feature usage
- Slow query detected
- Missing optional configuration
- Validation issues

```python
logger.warning(
    "Slow query detected",
    extra={
        'query_time_ms': duration * 1000,
        'threshold_ms': 1000,
        'model': 'Post',
    }
)
```

#### INFO
**Use for**: Important business events and normal operations

**Examples**:
- User registration
- Post published
- Asset uploaded
- Celery task completed
- Cache cleared

```python
logger.info(
    "Post published",
    extra={
        'post_slug': post.slug,
        'author': post.author.username,
        'word_count': post.word_count,
    }
)
```

#### DEBUG
**Use for**: Detailed diagnostic information (development only)

**Examples**:
- Function entry/exit
- Variable values
- API request/response details
- Database query details

```python
logger.debug(
    "Extracting metadata from image",
    extra={
        'asset_key': asset.key,
        'file_size': asset.file_size,
        'mime_type': asset.mime_type,
    }
)
```

### Module-Specific Logging Strategy

#### Models (`engine/models/`)
- **INFO**: Model creation, updates, deletion
- **WARNING**: Validation issues, data inconsistencies
- **ERROR**: Save failures, constraint violations

#### Views (`engine/views.py`)
- **INFO**: Page views, form submissions
- **WARNING**: Missing parameters, deprecated endpoints
- **ERROR**: View exceptions, render failures

#### Tasks (`engine/tasks.py`)
- **INFO**: Task start/completion
- **WARNING**: Retry attempts
- **ERROR**: Task failures

#### Admin (`engine/admin/`)
- **INFO**: Admin actions performed
- **WARNING**: Bulk operation warnings
- **ERROR**: Admin action failures

#### Signals (`engine/signals.py`)
- **INFO**: Signal triggered, operations performed
- **WARNING**: Edge cases, potential issues
- **ERROR**: Signal handler failures

#### Markdown Rendering (`engine/markdown/`)
- **DEBUG**: Rendering steps, processor execution
- **WARNING**: Invalid markdown, missing assets
- **ERROR**: Rendering failures

---

## Third-Party Services & Packages

### Recommended Stack

#### Tier 1: Essential (Implement First)

| Service/Package | Purpose | Cost | Priority |
|----------------|---------|------|----------|
| **python-json-logger** | Structured JSON logging | Free | ⭐⭐⭐⭐⭐ |
| **django-log-request-id** | Request ID tracking | Free | ⭐⭐⭐⭐⭐ |
| **Sentry** | Error tracking & performance | Free tier: 5k events/mo<br>$29/mo: 50k events | ⭐⭐⭐⭐⭐ |

#### Tier 2: Recommended (Add After Foundation)

| Service/Package | Purpose | Cost | Priority |
|----------------|---------|------|----------|
| **Papertrail** | Log aggregation & search | Free tier: 50MB/mo<br>$7/mo: 1GB | ⭐⭐⭐⭐ |
| **AWS CloudWatch** | Logs + metrics (if on AWS) | Pay-per-use | ⭐⭐⭐⭐ |
| **Datadog** | Full observability suite | $15/host/mo | ⭐⭐⭐ |
| **django-structlog** | Enhanced structured logging | Free | ⭐⭐⭐⭐ |

#### Tier 3: Advanced (Future Enhancement)

| Service/Package | Purpose | Cost | Priority |
|----------------|---------|------|----------|
| **Elasticsearch + Kibana** | Self-hosted log analytics | Self-hosted costs | ⭐⭐⭐ |
| **Grafana Loki** | Self-hosted log aggregation | Self-hosted costs | ⭐⭐⭐ |
| **New Relic** | APM + logging | $99/mo | ⭐⭐ |
| **Honeybadger** | Error tracking | $39/mo | ⭐⭐ |

### Detailed Recommendations

#### 🏆 Sentry (Highest Priority)

**Why Sentry**:
- ✅ Industry standard for Django error tracking
- ✅ Automatic exception capturing
- ✅ Performance monitoring (slow queries, N+1 problems)
- ✅ Release tracking (tie errors to deployments)
- ✅ User context (which users experience errors)
- ✅ Breadcrumbs (what happened before error)
- ✅ Source code integration
- ✅ Celery integration built-in

**Setup**:
```bash
uv add sentry-sdk
```

**Pricing**:
- **Free**: 5,000 events/month
- **Team**: $29/month for 50,000 events
- **Business**: $99/month for 200,000 events

**Best for**: All environments (dev, staging, prod)

---

#### 📋 Papertrail

**Why Papertrail**:
- ✅ Simple log aggregation
- ✅ Powerful search and filtering
- ✅ Real-time tail
- ✅ Alerts on log patterns
- ✅ Easy to set up
- ✅ Works with any logging format

**Setup**:
```python
# Add to LOGGING handlers
'papertrail': {
    'level': 'INFO',
    'class': 'logging.handlers.SysLogHandler',
    'address': ('logs.papertrailapp.com', YOUR_PORT),
    'formatter': 'json',
},
```

**Pricing**:
- **Free**: 50MB/month, 2-day retention
- **Basic**: $7/month for 1GB, 7-day retention
- **Pro**: $75/month for 10GB, 1-year retention

**Best for**: Development and staging log aggregation

---

#### 🔍 django-structlog

**Why django-structlog**:
- ✅ Better structured logging than python-json-logger
- ✅ Request ID middleware built-in
- ✅ Context processors
- ✅ Django-specific features

**Setup**:
```bash
uv add django-structlog
```

**Cost**: Free (open source)

**Best for**: Enhanced structured logging with Django integration

---

#### ☁️ AWS CloudWatch (if using AWS)

**Why CloudWatch**:
- ✅ Native AWS integration
- ✅ Metrics + logs in one place
- ✅ Alarms and dashboards
- ✅ Log insights for querying
- ✅ Long retention available

**Setup**:
```bash
uv add watchtower
```

```python
# Add to LOGGING handlers
'cloudwatch': {
    'level': 'INFO',
    'class': 'watchtower.CloudWatchLogHandler',
    'log_group': 'atproject',
    'stream_name': 'django',
    'formatter': 'json',
},
```

**Pricing**: Pay-per-use
- ~$0.50/GB ingested
- ~$0.03/GB stored per month

**Best for**: AWS-hosted applications

---

## Configuration Examples

### Development Environment

```python
# ATProject/settings.py (development)

LOGGING['handlers']['console']['level'] = 'DEBUG'
LOGGING['loggers']['']['level'] = 'DEBUG'
LOGGING['loggers']['django.db.backends']['level'] = 'DEBUG'  # Show SQL queries

# Don't send to external services in dev
# SENTRY_ENABLED = False
```

### Staging Environment

```python
# ATProject/settings.py (staging)

LOGGING['handlers']['console']['level'] = 'INFO'
LOGGING['loggers']['']['level'] = 'INFO'

# Enable Sentry with lower sample rate
sentry_sdk.init(
    dsn=env("SENTRY_DSN"),
    environment="staging",
    traces_sample_rate=0.5,  # 50% sampling
)
```

### Production Environment

```python
# ATProject/settings.py (production)

LOGGING['handlers']['console']['level'] = 'WARNING'
LOGGING['loggers']['']['level'] = 'INFO'
LOGGING['loggers']['django.db.backends']['level'] = 'WARNING'  # No SQL in prod

# Full Sentry configuration
sentry_sdk.init(
    dsn=env("SENTRY_DSN"),
    environment="production",
    traces_sample_rate=0.1,  # 10% sampling to control costs
    profiles_sample_rate=0.1,
)

# Add Papertrail
LOGGING['handlers']['papertrail'] = {
    'level': 'INFO',
    'class': 'logging.handlers.SysLogHandler',
    'address': ('logs.papertrailapp.com', env.int('PAPERTRAIL_PORT')),
    'formatter': 'json',
}
LOGGING['loggers']['']['handlers'].append('papertrail')
```

---

## Best Practices

### DO ✅

1. **Use Structured Logging**
   ```python
   logger.info(
       "Asset uploaded",
       extra={
           'asset_key': asset.key,
           'file_size': asset.file_size,
           'user_id': user.id,
       }
   )
   ```

2. **Include Context**
   ```python
   logger.error(
       "Failed to generate rendition",
       extra={
           'asset_key': asset.key,
           'requested_width': width,
           'error': str(e),
       },
       exc_info=True  # Include stack trace
   )
   ```

3. **Log Business Events**
   ```python
   logger.info("Post published", extra={'slug': post.slug})
   ```

4. **Use Request IDs**
   ```python
   logger.info(
       "Processing request",
       extra={'request_id': request.request_id}
   )
   ```

5. **Log Performance Metrics**
   ```python
   logger.info(
       "Query completed",
       extra={'duration_ms': duration * 1000, 'model': 'Post'}
   )
   ```

### DON'T ❌

1. **Log Sensitive Data**
   ```python
   # DON'T
   logger.info(f"User password: {password}")
   logger.info(f"API key: {api_key}")
   logger.info(f"Credit card: {cc_number}")
   ```

2. **Log in Tight Loops**
   ```python
   # DON'T
   for item in items:  # If items is large
       logger.debug(f"Processing {item}")  # Log flood

   # DO
   logger.info(f"Processing {len(items)} items")
   # Log every 100 items or significant events
   ```

3. **Catch and Suppress Exceptions**
   ```python
   # DON'T
   try:
       dangerous_operation()
   except Exception:
       pass  # Silent failure

   # DO
   try:
       dangerous_operation()
   except Exception as e:
       logger.error("Operation failed", exc_info=True)
       raise  # or handle appropriately
   ```

4. **Use String Formatting in Log Message**
   ```python
   # DON'T
   logger.info(f"User {user.username} logged in")  # Evaluated even if not logged

   # DO
   logger.info("User logged in", extra={'username': user.username})
   ```

5. **Log Everything at ERROR Level**
   ```python
   # DON'T
   logger.error("Starting function")  # This is DEBUG
   logger.error("User clicked button")  # This is INFO
   ```

---

## Monitoring & Alerting

### Key Metrics to Monitor

#### Application Health
- **Error rate**: Errors per minute/hour
- **Response time**: P50, P95, P99 percentiles
- **Request rate**: Requests per second
- **Success rate**: % of successful requests

#### Celery Tasks
- **Task queue length**: Pending tasks
- **Task success rate**: % of successful tasks
- **Task duration**: Average execution time
- **Failed tasks**: Count and types

#### Database
- **Query duration**: Slow queries (>1s)
- **Connection pool**: Active connections
- **Lock waits**: Blocked queries
- **Error rate**: DB exceptions

#### Storage (R2/S3)
- **Upload failures**: Failed asset uploads
- **Access errors**: 403/404 responses
- **Quota usage**: Storage used vs limit

### Recommended Alerts

#### Critical (Immediate Response)

```python
# Error rate spike
if error_rate > 10 per minute:
    alert(channel="pagerduty", severity="critical")

# Database down
if db_connection_errors > 3 in 5 minutes:
    alert(channel="pagerduty", severity="critical")

# Celery queue backup
if task_queue_length > 1000:
    alert(channel="pagerduty", severity="critical")
```

#### Warning (Review Soon)

```python
# Slow queries
if query_duration_p95 > 2 seconds:
    alert(channel="slack", severity="warning")

# High memory usage
if memory_usage > 80%:
    alert(channel="slack", severity="warning")

# Failed logins spike
if failed_logins > 10 per minute:
    alert(channel="email", severity="warning")
```

---

## Implementation Checklist

### Week 1: Foundation
- [ ] Add logging configuration to `settings.py`
- [ ] Create `logs/` directory
- [ ] Add `python-json-logger` to dependencies
- [ ] Add `django-log-request-id` to dependencies
- [ ] Create `.gitignore` entry for `logs/`
- [ ] Test logging in development

### Week 2: Middleware & Signals
- [ ] Create request logging middleware
- [ ] Create security logging signals
- [ ] Add Celery task logging
- [ ] Update existing modules to use logging
- [ ] Add logging to admin actions
- [ ] Add logging to model signals

### Week 3: External Services
- [ ] Sign up for Sentry account
- [ ] Configure Sentry in settings
- [ ] Test Sentry error capturing
- [ ] Set up Sentry performance monitoring
- [ ] Configure Sentry alerts

### Week 4: Monitoring & Alerts
- [ ] Set up Papertrail (or alternative)
- [ ] Create monitoring dashboard
- [ ] Configure critical alerts
- [ ] Document runbooks for alerts
- [ ] Test alert notifications

---

## Cost Estimate

### Recommended Setup

| Service | Tier | Monthly Cost |
|---------|------|--------------|
| Sentry | Team Plan | $29 |
| Papertrail | Basic Plan | $7 |
| **Total** | | **$36/month** |

### Enterprise Setup (Future)

| Service | Tier | Monthly Cost |
|---------|------|--------------|
| Sentry | Business Plan | $99 |
| Datadog | Pro Plan | $15/host × 3 = $45 |
| **Total** | | **$144/month** |

---

## Summary

### Recommended Immediate Actions

1. **Week 1**: Implement Django logging configuration
2. **Week 2**: Add request tracking and security logging
3. **Week 3**: Integrate Sentry for error tracking
4. **Week 4**: Set up Papertrail for log aggregation

### Quick Wins

✅ **No-cost improvements**:
- Add logging configuration to settings.py (1 hour)
- Add python-json-logger (15 minutes)
- Update existing loggers to use structured format (2 hours)

✅ **Low-cost, high-value**:
- Sentry free tier (5k events/month) - Perfect for starting out
- File-based logging with rotation - Free, works immediately

### Long-term Vision

```
Phase 1 (Now): Basic logging + Sentry
           ↓
Phase 2 (3 months): Add Papertrail, request tracking
           ↓
Phase 3 (6 months): Performance monitoring, custom dashboards
           ↓
Phase 4 (12 months): Full observability with Datadog/New Relic
```

---

**Next Steps**: Review this document and approve the implementation plan. Start with Phase 1 (Foundation) to establish basic logging infrastructure.
