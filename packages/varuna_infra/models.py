"""
VARUNA GRID — SQLAlchemy ORM Models.
"""
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint, Index, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID, BIGINT
from geoalchemy2 import Geometry

class Base(DeclarativeBase):
    pass

class CaseModel(Base):
    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    
    # PostGIS columns
    location = mapped_column(Geometry("POINT", srid=4326))
    bbox = mapped_column(Geometry("POLYGON", srid=4326))

    # Sequence tracker for concurrency-safe event ordering
    event_sequence_current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index('ix_cases_status', 'status'),
        Index('ix_cases_created_at', 'created_at', postgresql_ops={'created_at': 'DESC'}),
    )

class CaseEventModel(Base):
    __tablename__ = "case_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.case_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(256))

    __table_args__ = (
        UniqueConstraint('case_id', 'idempotency_key', name='uq_case_event_idempotency'),
        Index('ix_case_events_case_seq', 'case_id', 'sequence'),
        Index('ix_case_events_type', 'event_type'),
        Index('ix_case_events_ts', 'timestamp', postgresql_ops={'timestamp': 'DESC'}),
    )

class ArtifactModel(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.case_id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    produced_by: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128))
    storage_key: Mapped[Optional[str]] = mapped_column(String(512))
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index('ix_artifacts_case_id', 'case_id'),
        Index('ix_artifacts_type', 'artifact_type'),
        Index('ix_artifacts_created_at', 'created_at', postgresql_ops={'created_at': 'DESC'}),
    )

class VesselModel(Base):
    __tablename__ = "vessels"

    mmsi: Mapped[str] = mapped_column(String(16), primary_key=True)
    vessel_name: Mapped[Optional[str]] = mapped_column(String(256))
    vessel_type: Mapped[Optional[str]] = mapped_column(String(32))
    flag_state: Mapped[Optional[str]] = mapped_column(String(8))
    imo: Mapped[Optional[str]] = mapped_column(String(16))

class AisTrackModel(Base):
    __tablename__ = "ais_tracks"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    mmsi: Mapped[str] = mapped_column(String(16), ForeignKey("vessels.mmsi"))
    case_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("cases.case_id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    sog_knots: Mapped[Optional[float]] = mapped_column(Float)
    heading_deg: Mapped[Optional[float]] = mapped_column(Float)
    gap_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index('ix_ais_tracks_mmsi_ts', 'mmsi', 'timestamp'),
        Index('ix_ais_tracks_case_mmsi', 'case_id', 'mmsi'),
    )

class RecommendationModel(Base):
    __tablename__ = "recommendations"

    recommendation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.case_id"))
    decision_state: Mapped[Optional[str]] = mapped_column(String(32))
    latent_probability: Mapped[Optional[float]] = mapped_column(Float)
    top_posterior: Mapped[Optional[float]] = mapped_column(Float)
    distinguishability: Mapped[Optional[float]] = mapped_column(Float)
    candidates: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    envelope: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class DecisionModel(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.case_id"))
    recommendation_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("recommendations.recommendation_id"))
    human_officer_id: Mapped[Optional[str]] = mapped_column(String(64))
    human_decision: Mapped[Optional[str]] = mapped_column(String(32))
    override_reason: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
