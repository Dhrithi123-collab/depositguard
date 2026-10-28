from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    fdr_records: Mapped[list["FDRRecord"]] = relationship(back_populates="institution")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="institution")


class WorkflowConfiguration(Base):
    __tablename__ = "workflow_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    document_requirements: Mapped[list["DocumentRequirement"]] = relationship(back_populates="configuration")


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"
    __table_args__ = (UniqueConstraint("configuration_id", "requirement_key", name="uq_requirement_config_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    configuration_id: Mapped[str] = mapped_column(ForeignKey("workflow_configurations.id", ondelete="RESTRICT"), nullable=False, index=True)
    requirement_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    configuration: Mapped[WorkflowConfiguration] = relationship(back_populates="document_requirements")


class FDRRecord(Base):
    __tablename__ = "fdr_records"
    __table_args__ = (
        Index("ix_fdr_institution_instrument", "institution_id", "instrument_reference"),
        Index("ix_fdr_institution_stage", "institution_id", "workflow_stage"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True)
    instrument_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_stage: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    institution: Mapped[Institution] = relationship(back_populates="fdr_records")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="fdr_record")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_institution_created", "institution_id", "created_at"),
        Index("ix_audit_record_created", "fdr_record_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    fdr_record_id: Mapped[str | None] = mapped_column(ForeignKey("fdr_records.id", ondelete="RESTRICT"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    configuration_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    from_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    institution: Mapped[Institution] = relationship(back_populates="audit_events")
    fdr_record: Mapped[FDRRecord | None] = relationship(back_populates="audit_events")


class FDRRelationship(Base):
    """An explicitly recorded association between two FDR records in one institution."""

    __tablename__ = "fdr_relationships"
    __table_args__ = (
        UniqueConstraint(
            "institution_id", "source_record_id", "target_record_id", "relationship_type",
            name="uq_fdr_relationship_direction_type",
        ),
        CheckConstraint("source_record_id <> target_record_id", name="ck_fdr_relationship_not_self"),
        Index("ix_fdr_relationship_source_type", "institution_id", "source_record_id", "relationship_type"),
        Index("ix_fdr_relationship_target_type", "institution_id", "target_record_id", "relationship_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("fdr_records.id", ondelete="RESTRICT"), nullable=False)
    target_record_id: Mapped[str] = mapped_column(ForeignKey("fdr_records.id", ondelete="RESTRICT"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ReviewPriorityCalculation(Base):
    """Immutable per-calculation snapshot; queue membership is always recalculated from source data."""

    __tablename__ = "review_priority_calculations"
    __table_args__ = (
        Index("ix_priority_record_calculated", "institution_id", "fdr_record_id", "calculated_at"),
        Index("ix_priority_policy_calculated", "policy_version", "calculated_at"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_priority_score_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    fdr_record_id: Mapped[str] = mapped_column(ForeignKey("fdr_records.id", ondelete="RESTRICT"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_category_key: Mapped[str] = mapped_column(String(80), nullable=False)
    priority_category_label: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    factors: Mapped[list] = mapped_column(JSON, nullable=False)
    missing_inputs: Mapped[list] = mapped_column(JSON, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
