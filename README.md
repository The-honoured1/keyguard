<div align="center">

<h2>[KEYGUARD](https://pypi.org/project/keyguard-python/)</h2>

<img src="https://img.shields.io/badge/KeyGuard-API%20Gateway%20Library-6D28D9?style=for-the-badge&logo=python&logoColor=white" />

<h3>API key authentication, rate limiting, and abuse prevention<br>as a drop-in Python library.</h3>

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Zero Config](https://img.shields.io/badge/Setup-Zero%20Config-brightgreen.svg)](#zero-infrastructure-quick-start)
[![Redis](https://img.shields.io/badge/Redis-Optional-red.svg)](https://redis.io)

</div>

---

## Why KeyGuard?

Every API needs authentication and rate limiting. But setting up PostgreSQL, Redis, and Docker just to protect a few routes is overkill for most projects.

**KeyGuard works with zero infrastructure** — install it, add 3 lines of code, and your API is protected. When you're ready for production, swap in PostgreSQL and Redis with a config change.

---

## Zero-Infrastructure Quick Start

```bash
pip install keyguard-python .
```

```python
from fastapi import FastAPI
from keyguard import KeyGuard, KeyGuardConfig, KeyGuardMiddleware

app = FastAPI()

# That's it — SQLite database + in-memory rate limiting
kg = KeyGuard(KeyGuardConfig(secret_key="my-secret"))

app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api")

@app.on_event("startup")
async def startup():
    await kg.init_db()  # Creates a local keyguard.db file

@app.get("/api/data")
async def protected():
    return {"message": "Authorized!"}
```

**No Docker. No PostgreSQL. No Redis. Just `pip install` and go.**

```bash
# Create your first API key
python -m keyguard init
python -m keyguard create-org "My Project"
python -m keyguard --secret "my-secret" create-key --org "My Project" --label "dev-key"

# Test it
curl http://localhost:8000/api/data -H "X-API-KEY: kg_live_..."
```

---

## Table of Contents

- [Zero-Infrastructure Quick Start](#zero-infrastructure-quick-start)
- [CLI Tool](#cli-tool)
- [Admin API](#admin-api)
- [Production Setup](#production-setup)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Integration Guide](#integration-guide)
- [Rate Limiting](#rate-limiting-algorithm)
- [Security Model](#security-model)
- [Database Schema](#database-schema)
- [Scaling](#scaling-considerations)

---

## CLI Tool

Manage everything from the command line — no code required.

```bash
# Initialize the database
python -m keyguard init

# Create an organization
python -m keyguard create-org "Acme Corp"

# Generate an API key
python -m keyguard --secret "my-secret" create-key --org "Acme Corp" --label "production"

# List everything
python -m keyguard list-orgs
python -m keyguard list-keys

# Revoke a key
python -m keyguard revoke-key kg_live_4Gk9

# View usage stats
python -m keyguard stats
```

**Custom database and Redis:**

```bash
# Use PostgreSQL instead of SQLite
python -m keyguard --db "postgresql+asyncpg://user:pass@localhost/db" list-keys

# With Redis for rate limiting
python -m keyguard --redis "redis://localhost:6379/0" stats
```

### CLI Output Examples

```
$ python -m keyguard list-keys

Label                     Prefix          Org                  Status     Rate/min   Last Used
──────────────────────────────────────────────────────────────────────────────────────────────
production                kg_live_4Gk9    Acme Corp            active     120        2026-04-22 14:30
staging-key               kg_live_xR2m    Acme Corp            active     60         never
test-key                  kg_live_9pLq    Dev Team             revoked    30         2026-04-21 09:15

Total: 3 key(s)
```

```
$ python -m keyguard stats

╔══════════════════════════════════════╗
║        KeyGuard Statistics           ║
╠══════════════════════════════════════╣
║  Organizations:    2                 ║
║  Total Keys:       3                 ║
║  Active Keys:      2                 ║
║  Total Requests:   1,247             ║
║  Requests (1h):    83                ║
║  Error Rate:       2.4%              ║
╚══════════════════════════════════════╝
```

---

## Admin API

Mount a built-in admin router to manage KeyGuard via HTTP:

```python
from keyguard.api.admin import create_admin_router

app.include_router(
    create_admin_router(kg),
    prefix="/admin",
    tags=["KeyGuard Admin"]
)
```

All admin endpoints are protected by the `X-Admin-Key` header (your `secret_key`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/admin/orgs` | Create organization |
| `GET` | `/admin/orgs` | List organizations |
| `POST` | `/admin/keys` | Create API key (returns raw key once) |
| `GET` | `/admin/keys` | List all keys (masked) |
| `DELETE` | `/admin/keys/{id}` | Revoke a key |
| `GET` | `/admin/stats` | Usage statistics |

```bash
# Create an org
curl -X POST http://localhost:8000/admin/orgs \
  -H "X-Admin-Key: my-secret" \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp"}'

# Create a key
curl -X POST http://localhost:8000/admin/keys \
  -H "X-Admin-Key: my-secret" \
  -H "Content-Type: application/json" \
  -d '{"org_name": "Acme Corp", "label": "prod-key", "rate_limit_per_minute": 120}'

# List keys
curl http://localhost:8000/admin/keys -H "X-Admin-Key: my-secret"

# View stats
curl http://localhost:8000/admin/stats -H "X-Admin-Key: my-secret"
```

> **Tip**: Visit `http://localhost:8000/docs` to get an interactive Swagger UI for all admin endpoints.

---

## Production Setup

When you're ready for production, add PostgreSQL and Redis:

```bash
# Install production drivers
pip install -e ".[all]"

# Start infrastructure (optional Docker helper)
cd docker && docker compose up -d
```

```python
config = KeyGuardConfig(
    database_url="postgresql+asyncpg://user:pass@localhost/mydb",
    redis_url="redis://localhost:6379/0",
    secret_key="a-long-random-secret",
    default_rate_limit_per_minute=120,
)
```

| Setup | Database | Rate Limiter | Best For |
|-------|----------|-------------|----------|
| **Zero Config** | SQLite (file) | In-memory | Prototyping, small projects, single-process |
| **Production** | PostgreSQL | Redis | Multi-process, horizontal scaling, SaaS |

---

## Configuration

All configuration is passed via a `KeyGuardConfig` object:

```python
from keyguard import KeyGuardConfig

config = KeyGuardConfig(
    # Database — SQLite (default) or PostgreSQL
    database_url="sqlite+aiosqlite:///keyguard.db",

    # Redis — None (default, uses in-memory) or a Redis URL
    redis_url=None,

    # Security — pepper for key hashing
    secret_key="change-me",

    # Rate limiting defaults
    default_rate_limit_per_minute=60,
    ip_block_threshold=100,
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `database_url` | `sqlite+aiosqlite:///keyguard.db` | SQLite or PostgreSQL connection string |
| `redis_url` | `None` | Redis URL. `None` = in-memory rate limiting |
| `secret_key` | *(required)* | Secret pepper for key hashing |
| `default_rate_limit_per_minute` | `60` | Default quota for new keys |
| `ip_block_threshold` | `100` | Failed attempts before IP block |

---

## Architecture

```
Incoming Request
       │
       ▼
┌──────────────────────────────────┐
│        KeyGuardMiddleware        │  ← Hot Path
│                                  │
│  1. IP Blacklist check           │  ← Redis or In-Memory
│  2. Extract X-API-KEY header     │
│  3. Hash & validate key          │  ← SQLite or PostgreSQL
│  4. Sliding window rate limit    │  ← Redis or In-Memory
│  5. Attach key to request.state  │
│  6. Log usage (async)            │  ← SQLite or PostgreSQL
└──────────────────────────────────┘
       │
       ▼
  Your Route Handler


┌──────────────────────────────────┐
│           KeyGuard Core          │  ← Cold Path
│                                  │
│  • AuthService (key generation)  │
│  • RateLimitService (auto-pick)  │
│  • DB session factory            │
│  • CLI + Admin API               │
└──────────────────────────────────┘
```

KeyGuard automatically picks the right backend:
- No Redis URL → `MemoryRateLimitService` (in-memory deques)
- Redis URL set → `RateLimitService` (Redis sorted sets)
- `sqlite://` URL → SQLite via `aiosqlite`
- `postgresql://` URL → PostgreSQL via `asyncpg`

---

## Integration Guide

### 1. Adding Middleware

```python
# Protect all routes under /api
app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api")
```

Routes outside `protected_path` (e.g., `/health`, `/docs`, `/admin`) are unaffected.

### 2. Protecting Routes

Once middleware is applied, all routes under `protected_path` automatically:
- Return `401` if no key is provided
- Return `401` if the key is invalid or revoked
- Return `429` when the rate limit is exceeded
- Attach the key object to `request.state.api_key`

```python
from fastapi import Request

@app.get("/api/profile")
async def get_profile(request: Request):
    key = request.state.api_key   # Populated by KeyGuard
    return {
        "org_id": key.org_id,
        "key_label": key.label,
        "scopes": key.scopes
    }
```

### 3. IP-Based Rate Limiting & Lockouts

For routes that don't use API keys (like login, signup, or heavy tasks), use the `rate_limit_by_ip` dependency. It supports sliding windows, hard lockouts, and granular scoping.

```python
from keyguard import rate_limit_by_ip

# 1. Simple Rate Limit (5 per minute)
@app.post("/api/search", dependencies=[Depends(rate_limit_by_ip(kg, limit=5))])

# 2. Hard Lockout (24-hour block after 3 failures)
@app.post("/login", dependencies=[Depends(rate_limit_by_ip(kg, limit=3, lockout=86400))])

# 3. Scheduled Lockout (Block until 4:00 PM)
@app.post("/signup", dependencies=[Depends(rate_limit_by_ip(kg, limit=2, lockout="4:00 PM"))])

# 4. Global vs. Path Scope (default is "path")
# scope="path":   Only blocks access to THIS specific endpoint.
# scope="global": Blocks the IP from ALL KeyGuard-protected routes.
@app.post("/heavy-task", dependencies=[Depends(rate_limit_by_ip(kg, limit=1, scope="path"))])
```

### 4. Manual Logic-Based Blocking

You can manually trigger a lockout from within your route handlers based on your own business logic (e.g., failed payment or fraud detection) using `kg.block_request`.

```python
@app.post("/withdraw")
async def withdraw(request: Request):
    if fraud_detected:
        # Manually block this IP from /withdraw for 1 hour
        await kg.block_request(request, duration="1 hour", scope="path")
        return {"error": "Suspicious activity. Endpoint locked for 1 hour."}
```

### 5. Response Headers

**Response headers on every authorized request:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 43
```

### 6. Three Ways to Manage Keys

| Method | Best For |
|--------|----------|
| **CLI** (`python -m keyguard`) | Quick setup, scripting, CI/CD |
| **Admin API** (`/admin/keys`) | Web dashboards, frontends |
| **Programmatic** (Python code) | Custom logic, migrations |

---

## Rate Limiting Algorithm

KeyGuard uses the **Sliding Window Log** algorithm.

**Redis mode**: Implemented with Redis Sorted Sets (`ZSET`) for distributed rate limiting across multiple processes.

**In-memory mode**: Implemented with Python `deque` + `asyncio.Lock` for single-process deployments.

```
Window: 60 seconds, Limit: 5 req/min

Timeline:
──────────────────────────────────────────▶ time
  t=0   t=10   t=40  t=59  t=61  t=62
  [req]  [req] [req] [req] [req] [req]
                                  ↑       ↑
                              5th hit   t=61: t=0 now out of window
                              BLOCKED   count = 4 → ALLOWED
```

---

## Security Model

### Key Generation
Keys use `secrets.token_urlsafe(32)` — cryptographically secure random bytes.

```
Format:  {prefix}{random_32_bytes_urlsafe_base64}
Example: kg_live_4Gk9mBX3pLqRsW...
```

### Key Storage
Raw keys are **never stored**. They're hashed with `SHA-256 + secret pepper`:

```
stored_hash = SHA-256(raw_key + SECRET_KEY)
```

### IP Abuse Prevention
Failed auth attempts are tracked per IP. After exceeding `ip_block_threshold`, the IP is blocked for 24 hours.

---

## Database Schema

KeyGuard creates three tables (works identically in SQLite and PostgreSQL):

```sql
organizations
├── id          VARCHAR(36) (PK)
├── name        VARCHAR
├── status      VARCHAR      -- 'active' | 'suspended'
└── created_at  DATETIME

api_keys
├── id                    VARCHAR(36) (PK)
├── org_id                VARCHAR(36) (FK → organizations)
├── label                 VARCHAR
├── prefix                VARCHAR
├── key_hash              VARCHAR (indexed)
├── is_active             BOOLEAN
├── scopes                JSON
├── rate_limit_per_minute  INTEGER
├── monthly_limit         BIGINT
├── created_at            DATETIME
├── expires_at            DATETIME
└── last_used_at          DATETIME

usage_logs
├── id          VARCHAR(36) (PK)
├── key_id      VARCHAR(36) (FK → api_keys)
├── path        VARCHAR
├── method      VARCHAR
├── status_code INTEGER
├── latency_ms  INTEGER
├── ip_address  VARCHAR
└── timestamp   DATETIME
```

---

## Scaling Considerations

| Scale Level | Setup |
|-------------|-------|
| **Hobby** (< 100 req/s) | SQLite + in-memory. Single process. |
| **Small** (< 1K req/s) | PostgreSQL + Redis. Single server. |
| **Medium** (< 50K req/s) | PostgreSQL + Redis. Multiple workers behind a load balancer. |
| **Large** (> 50K req/s) | Add Redis key caching, push logs to a queue (Kafka/SQS). |

---

## Development Setup

```bash
# Clone
git clone https://github.com/The-honoured1/keyguard
cd keyguard

# Create venv
python -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run the example (zero infrastructure!)
python example_integration.py

# Or use the CLI
python -m keyguard init
python -m keyguard create-org "Test"
python -m keyguard create-key --org "Test" --label "my-key"
```

**For production drivers:**

```bash
# PostgreSQL support
pip install -e ".[postgres]"

# Redis support
pip install -e ".[redis]"

# Everything
pip install -e ".[all]"
```

---

## Project Structure

```
keyguard/
├── keyguard/
│   ├── __init__.py          # Package exports
│   ├── __main__.py          # CLI entry point
│   ├── cli.py               # CLI commands
│   ├── config.py            # Configuration
│   ├── core.py              # KeyGuard core class
│   ├── middleware.py         # FastAPI middleware
│   ├── models.py            # Model re-exports
│   ├── api/
│   │   └── admin.py         # Admin API router
│   ├── db/
│   │   └── models.py        # SQLAlchemy models
│   ├── schemas/
│   │   └── admin.py         # Pydantic schemas
│   └── services/
│       ├── auth_service.py       # Key generation & hashing
│       ├── rate_limit_service.py # Redis rate limiter
│       └── memory_rate_limit.py  # In-memory rate limiter
├── docker/
│   └── docker-compose.yml   # Optional production infra
├── example_integration.py   # Working example
├── pyproject.toml
└── README.md
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <sub>Built with precision. Designed for simplicity.</sub>
</div>
