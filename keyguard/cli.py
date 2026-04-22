"""
KeyGuard CLI — manage API keys and organizations from the command line.

Usage:
    python -m keyguard init
    python -m keyguard create-org "My Company"
    python -m keyguard create-key --org "My Company" --label "dev-key"
    python -m keyguard list-orgs
    python -m keyguard list-keys
    python -m keyguard revoke-key <prefix>
    python -m keyguard stats
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from .config import KeyGuardConfig
from .core import KeyGuard


def _get_kg(args) -> KeyGuard:
    """Build a KeyGuard instance from CLI args."""
    kwargs = {}
    if args.db:
        kwargs["database_url"] = args.db
    if args.redis:
        kwargs["redis_url"] = args.redis
    if args.secret:
        kwargs["secret_key"] = args.secret
    return KeyGuard(KeyGuardConfig(**kwargs))


# ── Commands ──────────────────────────────────────────────────────

async def cmd_init(args):
    """Create all KeyGuard tables."""
    kg = _get_kg(args)
    await kg.init_db()
    print(f"✓ Database initialized: {kg.config.database_url}")


async def cmd_create_org(args):
    """Create a new organization."""
    from .models import Organization
    from sqlalchemy import select

    kg = _get_kg(args)
    await kg.init_db()

    async with kg.session_factory() as session:
        # Check for duplicate
        existing = await session.execute(
            select(Organization).where(Organization.name == args.name)
        )
        if existing.scalar_one_or_none():
            print(f"✗ Organization '{args.name}' already exists.")
            sys.exit(1)

        org = Organization(name=args.name)
        session.add(org)
        await session.commit()
        await session.refresh(org)
        print(f"✓ Organization created:")
        print(f"  Name: {org.name}")
        print(f"  ID:   {org.id}")


async def cmd_create_key(args):
    """Generate a new API key."""
    from .models import Organization, APIKey
    from sqlalchemy import select

    kg = _get_kg(args)
    await kg.init_db()

    async with kg.session_factory() as session:
        # Find org
        result = await session.execute(
            select(Organization).where(Organization.name == args.org)
        )
        org = result.scalar_one_or_none()
        if not org:
            print(f"✗ Organization '{args.org}' not found.")
            print(f"  Create one first: python -m keyguard create-org \"{args.org}\"")
            sys.exit(1)

        # Generate key
        prefix = args.prefix or "kg_live_"
        raw_key, key_hash = kg.auth.generate_api_key(prefix=prefix)
        rate_limit = args.rate_limit or kg.config.default_rate_limit_per_minute

        api_key = APIKey(
            org_id=org.id,
            label=args.label,
            prefix=raw_key[:12],
            key_hash=key_hash,
            rate_limit_per_minute=rate_limit,
            scopes=args.scopes.split(",") if args.scopes else ["read"],
        )
        session.add(api_key)
        await session.commit()

        print(f"✓ API key created:")
        print(f"  Label:      {args.label}")
        print(f"  Org:        {org.name}")
        print(f"  Rate Limit: {rate_limit}/min")
        print(f"  Scopes:     {api_key.scopes}")
        print()
        print(f"  ╔══════════════════════════════════════════════════════╗")
        print(f"  ║  API KEY (save this — it won't be shown again!)    ║")
        print(f"  ║  {raw_key:<52} ║")
        print(f"  ╚══════════════════════════════════════════════════════╝")


async def cmd_list_orgs(args):
    """List all organizations."""
    from .models import Organization
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    kg = _get_kg(args)

    async with kg.session_factory() as session:
        result = await session.execute(
            select(Organization).options(selectinload(Organization.api_keys))
        )
        orgs = result.scalars().all()

        if not orgs:
            print("No organizations found. Create one:")
            print("  python -m keyguard create-org \"My Company\"")
            return

        print(f"\n{'Name':<30} {'Status':<12} {'Keys':<8} {'ID'}")
        print("─" * 90)
        for org in orgs:
            key_count = len(org.api_keys) if org.api_keys else 0
            print(f"{org.name:<30} {org.status:<12} {key_count:<8} {org.id}")
        print(f"\nTotal: {len(orgs)} organization(s)")


async def cmd_list_keys(args):
    """List all API keys."""
    from .models import APIKey
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    kg = _get_kg(args)

    async with kg.session_factory() as session:
        result = await session.execute(
            select(APIKey).options(selectinload(APIKey.organization))
        )
        keys = result.scalars().all()

        if not keys:
            print("No API keys found. Create one:")
            print("  python -m keyguard create-key --org \"My Org\" --label \"my-key\"")
            return

        print(f"\n{'Label':<25} {'Prefix':<15} {'Org':<20} {'Status':<10} {'Rate/min':<10} {'Last Used'}")
        print("─" * 110)
        for k in keys:
            status = "active" if k.is_active else "revoked"
            org_name = k.organization.name if k.organization else "—"
            last_used = str(k.last_used_at)[:19] if k.last_used_at else "never"
            print(f"{k.label:<25} {k.prefix:<15} {org_name:<20} {status:<10} {k.rate_limit_per_minute:<10} {last_used}")
        print(f"\nTotal: {len(keys)} key(s)")


async def cmd_revoke_key(args):
    """Revoke a key by its prefix."""
    from .models import APIKey
    from sqlalchemy import select

    kg = _get_kg(args)

    async with kg.session_factory() as session:
        result = await session.execute(
            select(APIKey).where(APIKey.prefix.startswith(args.prefix))
        )
        key = result.scalar_one_or_none()

        if not key:
            print(f"✗ No key found with prefix '{args.prefix}'")
            sys.exit(1)

        if not key.is_active:
            print(f"Key '{key.label}' is already revoked.")
            return

        key.is_active = False
        await session.commit()
        print(f"✓ Key '{key.label}' (prefix: {key.prefix}) has been revoked.")


async def cmd_stats(args):
    """Show usage statistics."""
    from .models import Organization, APIKey, UsageLog
    from sqlalchemy import select, func

    kg = _get_kg(args)

    async with kg.session_factory() as session:
        org_count = (await session.execute(
            select(func.count(Organization.id))
        )).scalar() or 0

        total_keys = (await session.execute(
            select(func.count(APIKey.id))
        )).scalar() or 0

        active_keys = (await session.execute(
            select(func.count(APIKey.id)).where(APIKey.is_active == True)
        )).scalar() or 0

        total_requests = (await session.execute(
            select(func.count(UsageLog.id))
        )).scalar() or 0

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = (await session.execute(
            select(func.count(UsageLog.id)).where(UsageLog.timestamp >= one_hour_ago)
        )).scalar() or 0

        error_count = (await session.execute(
            select(func.count(UsageLog.id)).where(UsageLog.status_code >= 400)
        )).scalar() or 0
        error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0

        print(f"\n╔══════════════════════════════════════╗")
        print(f"║        KeyGuard Statistics           ║")
        print(f"╠══════════════════════════════════════╣")
        print(f"║  Organizations:    {org_count:<17} ║")
        print(f"║  Total Keys:       {total_keys:<17} ║")
        print(f"║  Active Keys:      {active_keys:<17} ║")
        print(f"║  Total Requests:   {total_requests:<17} ║")
        print(f"║  Requests (1h):    {recent:<17} ║")
        print(f"║  Error Rate:       {error_rate:<16.1f}% ║")
        print(f"╚══════════════════════════════════════╝")


# ── CLI Entry Point ───────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keyguard",
        description="KeyGuard CLI — API key management made simple.",
    )

    # Global options
    parser.add_argument(
        "--db", default=None,
        help="Database URL (default: sqlite+aiosqlite:///keyguard.db)"
    )
    parser.add_argument(
        "--redis", default=None,
        help="Redis URL (default: None, uses in-memory rate limiting)"
    )
    parser.add_argument(
        "--secret", default=None,
        help="Secret key for hashing API keys"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    subparsers.add_parser("init", help="Initialize database tables")

    # create-org
    p_org = subparsers.add_parser("create-org", help="Create an organization")
    p_org.add_argument("name", help="Organization name")

    # create-key
    p_key = subparsers.add_parser("create-key", help="Generate a new API key")
    p_key.add_argument("--org", required=True, help="Organization name")
    p_key.add_argument("--label", required=True, help="Key label/description")
    p_key.add_argument("--prefix", default=None, help="Key prefix (default: kg_live_)")
    p_key.add_argument("--rate-limit", type=int, default=None, help="Requests per minute")
    p_key.add_argument("--scopes", default=None, help="Comma-separated scopes (default: read)")

    # list-orgs
    subparsers.add_parser("list-orgs", help="List all organizations")

    # list-keys
    subparsers.add_parser("list-keys", help="List all API keys")

    # revoke-key
    p_revoke = subparsers.add_parser("revoke-key", help="Revoke an API key by prefix")
    p_revoke.add_argument("prefix", help="Key prefix to revoke")

    # stats
    subparsers.add_parser("stats", help="Show usage statistics")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "init": cmd_init,
        "create-org": cmd_create_org,
        "create-key": cmd_create_key,
        "list-orgs": cmd_list_orgs,
        "list-keys": cmd_list_keys,
        "revoke-key": cmd_revoke_key,
        "stats": cmd_stats,
    }

    cmd_func = commands.get(args.command)
    if not cmd_func:
        parser.print_help()
        sys.exit(1)

    asyncio.run(cmd_func(args))
