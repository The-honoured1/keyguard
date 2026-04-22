"""Pydantic schemas for the KeyGuard Admin API."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Organization Schemas ──────────────────────────────────────────

class OrgCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Organization name")


class OrgResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: Optional[datetime] = None
    key_count: int = 0

    model_config = {"from_attributes": True}


class OrgList(BaseModel):
    organizations: List[OrgResponse]
    total: int


# ── API Key Schemas ───────────────────────────────────────────────

class KeyCreate(BaseModel):
    org_name: str = Field(..., description="Organization name to create key under")
    label: str = Field(..., min_length=1, max_length=255, description="Human-readable key label")
    prefix: str = Field(default="kg_live_", description="Key prefix")
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    scopes: List[str] = Field(default=["read"], description="Permission scopes")


class KeyCreateResponse(BaseModel):
    """Response after creating a key — includes the raw key (shown only once)."""
    id: str
    label: str
    prefix: str
    raw_key: str = Field(..., description="Full API key — store securely, shown only once")
    rate_limit_per_minute: int
    scopes: List[str]
    org_name: str
    created_at: Optional[datetime] = None


class KeyResponse(BaseModel):
    id: str
    label: str
    prefix: str
    is_active: bool
    rate_limit_per_minute: int
    scopes: Optional[List[str]] = None
    org_name: str = ""
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KeyList(BaseModel):
    keys: List[KeyResponse]
    total: int


# ── Stats Schemas ─────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_organizations: int
    total_keys: int
    active_keys: int
    total_requests: int
    recent_requests_1h: int
    top_keys: List[dict]
    error_rate: float = 0.0
