"""
KeyGuard Admin API Router.

Provides a mountable FastAPI router for managing organizations,
API keys, and viewing usage stats. Protected by the admin secret key.

Usage:
    from keyguard.api.admin import create_admin_router

    app.include_router(
        create_admin_router(kg),
        prefix="/admin",
        tags=["KeyGuard Admin"]
    )
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from ..models import Organization, APIKey, UsageLog
from ..schemas.admin import (
    OrgCreate, OrgResponse, OrgList,
    KeyCreate, KeyCreateResponse, KeyResponse, KeyList,
    StatsResponse,
)


def create_admin_router(kg_instance) -> APIRouter:
    """Creates a FastAPI router with admin CRUD endpoints for KeyGuard.

    Args:
        kg_instance: A configured KeyGuard instance.

    Returns:
        APIRouter with all admin endpoints.
    """
    router = APIRouter()
    kg = kg_instance

    async def _verify_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")):
        """Dependency that verifies the admin secret key."""
        if x_admin_key != kg.config.secret_key:
            raise HTTPException(status_code=403, detail="Invalid admin key.")
        return True

    # ── Organizations ─────────────────────────────────────────────

    @router.post("/orgs", response_model=OrgResponse)
    async def create_org(body: OrgCreate, _=Depends(_verify_admin)):
        """Create a new organization."""
        async with kg.session_factory() as session:
            # Check for duplicate
            existing = await session.execute(
                select(Organization).where(Organization.name == body.name)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(400, f"Organization '{body.name}' already exists.")

            org = Organization(name=body.name)
            session.add(org)
            await session.commit()
            await session.refresh(org)
            return OrgResponse(
                id=org.id,
                name=org.name,
                status=org.status,
                created_at=org.created_at,
                key_count=0,
            )

    @router.get("/orgs", response_model=OrgList)
    async def list_orgs(_=Depends(_verify_admin)):
        """List all organizations with their key counts."""
        async with kg.session_factory() as session:
            result = await session.execute(
                select(Organization).options(selectinload(Organization.api_keys))
            )
            orgs = result.scalars().all()
            items = [
                OrgResponse(
                    id=o.id,
                    name=o.name,
                    status=o.status,
                    created_at=o.created_at,
                    key_count=len(o.api_keys),
                )
                for o in orgs
            ]
            return OrgList(organizations=items, total=len(items))

    # ── API Keys ──────────────────────────────────────────────────

    @router.post("/keys", response_model=KeyCreateResponse)
    async def create_key(body: KeyCreate, _=Depends(_verify_admin)):
        """Create a new API key. The raw key is returned only once."""
        async with kg.session_factory() as session:
            # Find org
            result = await session.execute(
                select(Organization).where(Organization.name == body.org_name)
            )
            org = result.scalar_one_or_none()
            if not org:
                raise HTTPException(404, f"Organization '{body.org_name}' not found.")

            # Generate key
            raw_key, key_hash = kg.auth.generate_api_key(prefix=body.prefix)
            api_key = APIKey(
                org_id=org.id,
                label=body.label,
                prefix=raw_key[:12],
                key_hash=key_hash,
                rate_limit_per_minute=body.rate_limit_per_minute,
                scopes=body.scopes,
            )
            session.add(api_key)
            await session.commit()
            await session.refresh(api_key)

            return KeyCreateResponse(
                id=api_key.id,
                label=api_key.label,
                prefix=api_key.prefix,
                raw_key=raw_key,
                rate_limit_per_minute=api_key.rate_limit_per_minute,
                scopes=api_key.scopes or [],
                org_name=org.name,
                created_at=api_key.created_at,
            )

    @router.get("/keys", response_model=KeyList)
    async def list_keys(_=Depends(_verify_admin)):
        """List all API keys (hash is never exposed)."""
        async with kg.session_factory() as session:
            result = await session.execute(
                select(APIKey).options(selectinload(APIKey.organization))
            )
            keys = result.scalars().all()
            items = [
                KeyResponse(
                    id=k.id,
                    label=k.label,
                    prefix=k.prefix,
                    is_active=k.is_active,
                    rate_limit_per_minute=k.rate_limit_per_minute,
                    scopes=k.scopes,
                    org_name=k.organization.name if k.organization else "",
                    created_at=k.created_at,
                    last_used_at=k.last_used_at,
                )
                for k in keys
            ]
            return KeyList(keys=items, total=len(items))

    @router.delete("/keys/{key_id}")
    async def revoke_key(key_id: str, _=Depends(_verify_admin)):
        """Revoke (deactivate) an API key by its ID."""
        async with kg.session_factory() as session:
            result = await session.execute(
                select(APIKey).where(APIKey.id == key_id)
            )
            key = result.scalar_one_or_none()
            if not key:
                raise HTTPException(404, "Key not found.")

            key.is_active = False
            await session.commit()
            return {"detail": f"Key '{key.label}' revoked.", "key_id": key_id}

    # ── Stats ─────────────────────────────────────────────────────

    @router.get("/stats", response_model=StatsResponse)
    async def get_stats(_=Depends(_verify_admin)):
        """Get usage statistics across all keys."""
        async with kg.session_factory() as session:
            # Counts
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

            # Recent requests (last 1 hour)
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            recent_requests = (await session.execute(
                select(func.count(UsageLog.id)).where(
                    UsageLog.timestamp >= one_hour_ago
                )
            )).scalar() or 0

            # Error rate
            error_count = (await session.execute(
                select(func.count(UsageLog.id)).where(
                    UsageLog.status_code >= 400
                )
            )).scalar() or 0
            error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0.0

            # Top keys by usage
            top_keys_result = await session.execute(
                select(
                    APIKey.label,
                    APIKey.prefix,
                    func.count(UsageLog.id).label("request_count"),
                )
                .join(UsageLog, UsageLog.key_id == APIKey.id)
                .group_by(APIKey.id, APIKey.label, APIKey.prefix)
                .order_by(func.count(UsageLog.id).desc())
                .limit(5)
            )
            top_keys = [
                {"label": r.label, "prefix": r.prefix, "requests": r.request_count}
                for r in top_keys_result
            ]

            return StatsResponse(
                total_organizations=org_count,
                total_keys=total_keys,
                active_keys=active_keys,
                total_requests=total_requests,
                recent_requests_1h=recent_requests,
                top_keys=top_keys,
                error_rate=round(error_rate, 2),
            )

    return router
