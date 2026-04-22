from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class APIKeyBase(BaseModel):
    label: str
    rate_limit_per_minute: int = 60
    scopes: List[str] = []

class APIKeyCreate(APIKeyBase):
    org_id: UUID

class APIKeyResponse(APIKeyBase):
    id: UUID
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class APIKeyWithRaw(APIKeyResponse):
    raw_key: str

class OrganizationCreate(BaseModel):
    name: str

class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
