from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.db.base import get_db
from app.db.models import Organization, APIKey
from app.schemas.api_models import OrganizationCreate, OrganizationResponse, APIKeyCreate, APIKeyWithRaw, APIKeyResponse
from app.services.auth_service import auth_service

router = APIRouter()

@router.post("/organizations", response_model=OrganizationResponse)
async def create_organization(org_in: OrganizationCreate, db: AsyncSession = Depends(get_db)):
    org = Organization(name=org_in.name)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org

@router.get("/organizations", response_model=List[OrganizationResponse])
async def list_organizations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization))
    return result.scalars().all()

@router.post("/keys", response_model=APIKeyWithRaw)
async def create_api_key(key_in: APIKeyCreate, db: AsyncSession = Depends(get_db)):
    # 1. Verify organization exists
    org_result = await db.execute(select(Organization).where(Organization.id == key_in.org_id))
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # 2. Generate key
    raw_key, key_hash = auth_service.generate_api_key()

    # 3. Store in DB
    api_key = APIKey(
        org_id=key_in.org_id,
        label=key_in.label,
        prefix=raw_key[:8], # kg_live_
        key_hash=key_hash,
        rate_limit_per_minute=key_in.rate_limit_per_minute,
        scopes=key_in.scopes
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    # Return with raw key (only shown once)
    response_data = APIKeyWithRaw.model_validate(api_key)
    response_data.raw_key = raw_key
    return response_data

@router.get("/keys/{org_id}", response_model=List[APIKeyResponse])
async def list_keys(org_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(APIKey).where(APIKey.org_id == org_id))
    return result.scalars().all()
