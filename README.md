<div align="center">

<img src="https://img.shields.io/badge/KeyGuard-API%20Gateway%20Library-6D28D9?style=for-the-badge&logo=python&logoColor=white" />

<h3>Production-grade API key authentication, rate limiting, and abuse prevention<br>as a drop-in Python library.</h3>

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Redis](https://img.shields.io/badge/Redis-Optional-red.svg)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org)

</div>

---

## Overview

**KeyGuard** is a lightweight, production-ready Python library that gives your FastAPI application a full API gateway layer in under 10 lines of code.

It handles the hard stuff that every SaaS backend needs:

- 🔑 **API Key Lifecycle** — Generate, validate, and revoke keys with one-way hashed storage
- ⏱️ **Sliding Window Rate Limiting** — Per-key quotas backed by Redis for millisecond precision
- 🛡️ **IP Abuse Prevention** — Automatic blacklisting for repeated unauthorized requests
- 📊 **Request Logging** — Per-request latency and usage tracking stored in PostgreSQL
- 🏢 **Multi-Tenant** — Organize keys under organizations for SaaS-style access control

> Inspired by how Stripe, Cloudflare, and AWS API Gateway work — simplified for real Python backends.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Integration Guide](#integration-guide)
  - [Adding Middleware](#1-adding-middleware)
  - [Initializing the Database](#2-initializing-the-database)
  - [Creating Organizations & Keys](#3-creating-organizations--keys)
  - [Protecting Routes](#4-protecting-routes)
- [Rate Limiting Algorithm](#rate-limiting-algorithm)
- [Security Model](#security-model)
- [Database Schema](#database-schema)
- [Scaling Considerations](#scaling-considerations)
- [Development Setup](#development-setup)
- [License](#license)

---

## Quick Start

```python
from fastapi import FastAPI
from keyguard import KeyGuard, KeyGuardConfig, KeyGuardMiddleware

app = FastAPI()

# 1. Configure KeyGuard
config = KeyGuardConfig(
    database_url="postgresql+asyncpg://user:pass@localhost/mydb",
    redis_url="redis://localhost:6379/0",
    secret_key="your-secret-pepper-key"
)

# 2. Initialize the core instance
kg = KeyGuard(config)

# 3. Register middleware to protect your /api routes
app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api")

# 4. Initialize database tables on startup
@app.on_event("startup")
async def startup():
    await kg.init_db()

# Any route under /api is now protected
@app.get("/api/data")
async def protected_data():
    return {"message": "Authorized!"}
```

```bash
# Access a protected route
curl http://localhost:8000/api/data -H "X-API-KEY: kg_live_your_key_here"

# Missing key → 401
# Wrong key  → 401
# Too many   → 429 with X-RateLimit-Remaining: 0
```

---

## Installation

```bash
# From source (recommended for now)
git clone https://github.com/The-honoured1/keyguard
cd keyguard
pip install -e .
```

**Dependencies automatically installed:**
- `fastapi` — Web framework
- `sqlalchemy[asyncio]` + `asyncpg` — Async PostgreSQL
- `redis` — Rate limiting backend
- `pydantic` — Configuration validation
- `passlib` — Password/secret utilities

---

## Architecture

KeyGuard is designed around two core concepts: a **hot path** (executed for every request) and a **cold path** (management and analytics).

```
Incoming Request
       │
       ▼
┌──────────────────────────────────┐
│        KeyGuardMiddleware        │  ← Hot Path
│                                  │
│  1. IP Blacklist check (Redis)   │
│  2. Extract X-API-KEY header     │
│  3. Hash & validate key (DB)     │
│  4. Sliding window rate limit    │
│  5. Attach key to request.state  │
│  6. Log usage (Postgres, async)  │
└──────────────────────────────────┘
       │
       ▼
  Your Route Handler


┌──────────────────────────────────┐
│           KeyGuard Core          │  ← Cold Path
│                                  │
│  • AuthService (key generation)  │
│  • RateLimitService              │
│  • DB session factory            │
│  • init_db() utility             │
└──────────────────────────────────┘
```

---

## Configuration

All configuration is passed via a `KeyGuardConfig` object. No `.env` file is required.

```python
from keyguard import KeyGuardConfig

config = KeyGuardConfig(
    # Required
    database_url="postgresql+asyncpg://user:pass@localhost/db",
    redis_url="redis://localhost:6379/0",
    secret_key="a-long-random-secret-for-key-hashing",

    # Optional — with sensible defaults
    default_rate_limit_per_minute=60,   # Default quota for new keys
    ip_block_threshold=100,             # Failed attempts before IP ban
    auto_init_db=True                   # Auto-create tables on init_db()
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `database_url` | `postgresql+asyncpg://...` | Async PostgreSQL connection string |
| `redis_url` | `redis://localhost:6379/0` | Redis connection string |
| `secret_key` | *(required)* | Pepper used when hashing keys |
| `default_rate_limit_per_minute` | `60` | Default new key quota |
| `ip_block_threshold` | `100` | Auth failures before IP block |

---

## Integration Guide

### 1. Adding Middleware

```python
# Protect all routes under /api
app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api")

# Or a more specific prefix
app.add_middleware(KeyGuardMiddleware, kg_instance=kg, protected_path="/api/v1")
```

Routes outside the `protected_path` (e.g., `/health`, `/docs`) are completely unaffected.

---

### 2. Initializing the Database

KeyGuard creates its own tables inside your database without interfering with your app's existing schema.

```python
@app.on_event("startup")
async def startup():
    await kg.init_db()  # Creates organizations, api_keys, usage_logs tables
```

---

### 3. Creating Organizations & Keys

KeyGuard's management interface is entirely programmatic — ideal for embedding into your own admin panel, CLI, or setup scripts.

```python
from keyguard.models import Organization, APIKey

async def create_org_and_key(session):
    # Create an Organisation
    org = Organization(name="Acme Corp")
    session.add(org)
    await session.flush()

    # Generate an API Key
    raw_key, key_hash = kg.auth.generate_api_key(prefix="kg_live_")

    key = APIKey(
        org_id=org.id,
        label="Production App Key",
        prefix=raw_key[:8],
        key_hash=key_hash,
        rate_limit_per_minute=120,      # Custom quota
        scopes=["read", "write"]        # Extensible scopes
    )
    session.add(key)
    await session.commit()

    print(f"API Key (show once): {raw_key}")
    return raw_key

# Use the session factory from KeyGuard
async with kg.session_factory() as session:
    await create_org_and_key(session)
```

> **Security note**: The `raw_key` is only available at creation time. After hashing, it cannot be recovered. Store it securely and show it to the user once.

---

### 4. Protecting Routes

Once the middleware is applied, all routes under `protected_path` automatically:
- Return `401` if no key is provided
- Return `401` if the key is invalid or revoked
- Return `429` when the rate limit is exceeded
- Attach the key object to `request.state.api_key` for use in your handler

```python
from fastapi import Request

@app.get("/api/profile")
async def get_profile(request: Request):
    key = request.state.api_key   # Populated by KeyGuard
    return {
        "org_id": str(key.org_id),
        "key_label": key.label,
        "scopes": key.scopes
    }
```

**Response Headers on every authorized request:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 43
```

---

## Rate Limiting Algorithm

KeyGuard uses the **Sliding Window Log** algorithm, implemented with Redis Sorted Sets (`ZSET`).

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

**Why Sliding Window Log over Fixed Window?**

| Algorithm | Accuracy | Redis Cost | Burst Tolerance |
|-----------|----------|------------|-----------------|
| Fixed Window | Low (burst at boundary) | Very low | Poor |
| Sliding Window Counter | Medium | Low | Good |
| **Sliding Window Log** | **High (exact)** | **Medium** | **Excellent** |

For most SaaS use cases, the precision of the Sliding Window Log is worth the slightly higher Redis memory cost.

---

## Security Model

### Key Generation
Keys are generated using Python's `secrets.token_urlsafe(32)` — cryptographically secure random bytes encoded in URL-safe Base64.

```
Final key format: {prefix}{random_32_bytes_urlsafe_base64}
Example:          kg_live_4Gk9mBX3pLqRsW...
```

### Key Storage
**Raw keys are never stored.** Keys are hashed with `SHA-256 + secret pepper` before being written to the database:

```
stored_hash = SHA-256(raw_key + SECRET_KEY)
```

Even if your database is fully compromised, the raw keys cannot be recovered without the `SECRET_KEY`.

### IP Abuse Prevention
Every failed authentication attempt (wrong key, missing key) is tracked per IP in Redis. Once an IP exceeds the `ip_block_threshold`, it is blocked for 24 hours.

```
Abuse tracking key:   abuse:{ip}   (Counter, 1hr TTL)
Blacklist key:        block:{ip}   (Flag, 24hr TTL)
```

---

## Database Schema

KeyGuard creates three tables in your database:

```sql
organizations
├── id          UUID (PK)
├── name        VARCHAR
├── status      VARCHAR  -- 'active' | 'suspended'
└── created_at  TIMESTAMPTZ

api_keys
├── id                    UUID (PK)
├── org_id                UUID (FK → organizations)
├── label                 VARCHAR
├── prefix                VARCHAR     -- e.g. 'kg_live_'
├── key_hash              VARCHAR     -- SHA-256 hash, indexed
├── is_active             BOOLEAN
├── scopes                JSONB       -- ["read", "write"]
├── rate_limit_per_minute INTEGER
├── monthly_limit         BIGINT
├── created_at            TIMESTAMPTZ
├── expires_at            TIMESTAMPTZ
└── last_used_at          TIMESTAMPTZ

usage_logs
├── id          UUID (PK)
├── key_id      UUID (FK → api_keys)
├── path        VARCHAR
├── method      VARCHAR
├── status_code INTEGER
├── latency_ms  INTEGER
├── ip_address  VARCHAR
└── timestamp   TIMESTAMPTZ
```

---

## Scaling Considerations

KeyGuard is designed to scale horizontally without any changes.

| Scale Level | Architecture |
|-------------|-------------|
| **Small** (< 1K req/s) | Single FastAPI + Postgres + Redis instance |
| **Medium** (< 50K req/s) | Multiple FastAPI instances behind a load balancer. Redis handles shared rate limit state. |
| **Large** (> 50K req/s) | Cache key metadata in Redis to eliminate per-request DB reads. Push `usage_logs` to a queue (Kafka/SQS) instead of writing synchronously. |

**Recommended optimizations for high traffic:**
1. **Redis Key Cache**: Cache the API key object in Redis with a short TTL (e.g., 30s) to avoid PostgreSQL on every hot path request.
2. **Async Logging**: Push `UsageLog` entries to a background job queue to prevent database writes from adding latency to the hot path.
3. **Read Replicas**: Point the admin queries (stats, logs) to a Postgres read replica.

---

## Development Setup

```bash
# Clone the repo
git clone https://github.com/The-honoured1/keyguard
cd keyguard

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install KeyGuard with dev dependencies
pip install -e ".[dev]"

# Start infrastructure
docker compose up -d  # Starts Postgres + Redis

# Run the example integration
uvicorn example_integration:app --reload
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <sub>Built with precision. Designed for production.</sub>
</div>
