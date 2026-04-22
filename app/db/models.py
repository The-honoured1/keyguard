from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, JSON, BigInteger
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    status = Column(String, default="active")  # active, suspended
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    api_keys = relationship("APIKey", back_populates="organization", cascade="all, delete-orphan")

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    label = Column(String, nullable=False)
    prefix = Column(String, nullable=False)  # e.g., kg_live_
    key_hash = Column(String, unique=True, nullable=False, index=True)
    
    is_active = Column(Boolean, default=True)
    scopes = Column(JSON, default=list)  # ["read", "write"]
    
    # Quota Limits
    rate_limit_per_minute = Column(Integer, default=60)
    monthly_limit = Column(BigInteger, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="api_keys")
    usage_logs = relationship("UsageLog", back_populates="api_key", cascade="all, delete-orphan")

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)
    path = Column(String, nullable=False)
    method = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    ip_address = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    api_key = relationship("APIKey", back_populates="usage_logs")
