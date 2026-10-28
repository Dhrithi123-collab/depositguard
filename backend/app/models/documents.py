from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.domain import utc_now


class FDRDocument(Base):
    __tablename__ = "fdr_documents"
    __table_args__ = (
        Index("ix_document_institution_record", "institution_id", "fdr_record_id"),
        Index("ix_document_record_category", "fdr_record_id", "category_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    fdr_record_id: Mapped[str] = mapped_column(ForeignKey("fdr_records.id", ondelete="RESTRICT"), nullable=False)
    category_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    versions: Mapped[list["FDRDocumentVersion"]] = relationship(back_populates="document", order_by="FDRDocumentVersion.version_number")


class FDRDocumentVersion(Base):
    __tablename__ = "fdr_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        UniqueConstraint("storage_id", name="uq_document_storage_id"),
        CheckConstraint("version_number >= 1", name="ck_document_version_positive"),
        CheckConstraint("byte_size > 0", name="ck_document_version_size_positive"),
        CheckConstraint("length(sha256_digest) = 64", name="ck_document_sha256_length"),
        Index("ix_document_version_config", "configuration_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("fdr_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    configuration_id: Mapped[str] = mapped_column(ForeignKey("workflow_configurations.id", ondelete="RESTRICT"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_id: Mapped[str] = mapped_column(String(32), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    digest_algorithm: Mapped[str] = mapped_column(String(20), default="sha256", nullable=False)
    upload_policy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    upload_policy_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(120), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    document: Mapped[FDRDocument] = relationship(back_populates="versions")
    configuration = relationship("WorkflowConfiguration")


class EvidenceCheck(Base):
    __tablename__ = "evidence_checks"
    __table_args__ = (
        CheckConstraint("result_status IN ('PASS', 'FAIL', 'INDETERMINATE')", name="ck_evidence_result_status"),
        Index("ix_evidence_institution_record_time", "institution_id", "fdr_record_id", "executed_at"),
        Index("ix_evidence_document_version", "document_version_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False)
    fdr_record_id: Mapped[str] = mapped_column(ForeignKey("fdr_records.id", ondelete="RESTRICT"), nullable=False)
    document_version_id: Mapped[str | None] = mapped_column(ForeignKey("fdr_document_versions.id", ondelete="RESTRICT"), nullable=True)
    check_type: Mapped[str] = mapped_column(String(80), nullable=False)
    result_status: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    software_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_references: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    result_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    human_review_decision: Mapped[str | None] = mapped_column(String(500), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
