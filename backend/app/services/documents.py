from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, DocumentRequirement, EvidenceCheck, FDRDocument, FDRDocumentVersion, FDRRecord, WorkflowConfiguration
from app.schemas.uploads import (
    DocumentResponse,
    DocumentVersionResponse,
    EvidenceCheckResponse,
)
from app.services.storage import (
    PrivateLocalStorage,
    StorageUnavailable,
    UploadPolicyLoader,
    UploadPolicyError,
)
from app.services.workflow import EntityNotFound, WorkflowConfigurationError, WorkflowService

INTEGRITY_SOFTWARE_VERSION = "depositguard-sha256-v1"


class DocumentCategoryNotConfigured(Exception):
    pass


class DocumentVersionConflict(Exception):
    pass


class DocumentService:
    def __init__(
        self,
        storage: PrivateLocalStorage,
        policy_loader: UploadPolicyLoader,
        workflow: WorkflowService,
    ):
        self.storage = storage
        self.policy_loader = policy_loader
        self.workflow = workflow

    @staticmethod
    def _record_for_scope(db: Session, institution_id: str, record_id: str) -> FDRRecord:
        record = db.scalar(
            select(FDRRecord).where(
                FDRRecord.id == record_id,
                FDRRecord.institution_id == institution_id,
            )
        )
        if record is None:
            raise EntityNotFound("FDR record was not found for this institution.")
        return record

    @staticmethod
    def _version_response(version: FDRDocumentVersion, configuration_version: str) -> DocumentVersionResponse:
        return DocumentVersionResponse(
            id=version.id,
            document_id=version.document_id,
            configuration_version=configuration_version,
            version_number=version.version_number,
            original_filename=version.original_filename,
            byte_size=version.byte_size,
            media_type=version.media_type,
            digest_algorithm=version.digest_algorithm,
            sha256_digest=version.sha256_digest,
            uploaded_by=version.uploaded_by,
            upload_policy_version=version.upload_policy_version,
            upload_policy_digest=version.upload_policy_digest,
            uploaded_at=version.uploaded_at,
        )

    def _document_response(self, db: Session, document: FDRDocument) -> DocumentResponse:
        latest = db.scalar(
            select(FDRDocumentVersion)
            .where(FDRDocumentVersion.document_id == document.id)
            .order_by(FDRDocumentVersion.version_number.desc())
            .limit(1)
        )
        latest_response = None
        if latest is not None:
            configuration = db.get(WorkflowConfiguration, latest.configuration_id)
            latest_response = self._version_response(latest, configuration.version)
        return DocumentResponse(
            id=document.id,
            institution_id=document.institution_id,
            fdr_record_id=document.fdr_record_id,
            category_key=document.category_key,
            created_by=document.created_by,
            created_at=document.created_at,
            latest_version=latest_response,
        )

    async def upload_async(
        self,
        db: Session,
        institution_id: str,
        record_id: str,
        category_key: str,
        actor_id: str,
        upload: UploadFile,
        document_id: str | None = None,
    ) -> DocumentResponse:
        """Run the file read asynchronously while retaining transactional database writes."""
        policy = self.policy_loader.load()
        policy_digest = self.policy_loader.digest(policy)
        workflow_config = self.workflow.load_configuration()
        record = self._record_for_scope(db, institution_id, record_id)
        recorded_policy_digest = db.scalar(
            select(FDRDocumentVersion.upload_policy_digest)
            .where(
                FDRDocumentVersion.upload_policy_version == policy.version,
                FDRDocumentVersion.upload_policy_digest.is_not(None),
            )
            .limit(1)
        )
        if recorded_policy_digest is not None and recorded_policy_digest != policy_digest:
            raise UploadPolicyError("Upload policy versions are immutable; use a new version for changed content.")
        requirement_config = next(
            (item for item in workflow_config.document_requirements if item.key == category_key),
            None,
        )
        if requirement_config is None:
            raise DocumentCategoryNotConfigured("Document category is not defined by the active configuration.")
        document = None
        if document_id is not None:
            document = db.scalar(
                select(FDRDocument).where(
                    FDRDocument.id == document_id,
                    FDRDocument.institution_id == institution_id,
                    FDRDocument.fdr_record_id == record_id,
                )
            )
            if document is None:
                raise EntityNotFound("Document was not found for this institution and FDR record.")
            if document.category_key != category_key:
                raise DocumentVersionConflict("A document version must retain its original category.")

        stored = await self.storage.store_upload(upload, policy)
        try:
            configuration_snapshot = self.workflow.store_configuration(db, workflow_config)
            if document is None:
                document = FDRDocument(
                    institution_id=institution_id,
                    fdr_record_id=record.id,
                    category_key=category_key,
                    created_by=actor_id,
                )
                db.add(document)
                db.flush()
            latest_number = db.scalar(
                select(func.max(FDRDocumentVersion.version_number)).where(
                    FDRDocumentVersion.document_id == document.id
                )
            )
            version_number = (latest_number or 0) + 1
            version = FDRDocumentVersion(
                document_id=document.id,
                configuration_id=configuration_snapshot.id,
                version_number=version_number,
                original_filename=stored.original_filename,
                storage_id=stored.storage_id,
                byte_size=stored.byte_size,
                media_type=stored.media_type,
                sha256_digest=stored.sha256_digest,
                digest_algorithm="sha256",
                upload_policy_version=policy.version,
                upload_policy_digest=policy_digest,
                uploaded_by=actor_id,
            )
            db.add(version)
            db.flush()
            db.add(
                AuditEvent(
                    institution_id=institution_id,
                    fdr_record_id=record.id,
                    event_type="document_uploaded",
                    actor_id=actor_id,
                    configuration_version=configuration_snapshot.version,
                    details={
                        "category_key": document.category_key,
                        "document_id": document.id,
                        "document_version_id": version.id,
                        "version_number": version_number,
                        "upload_policy_version": policy.version,
                    },
                )
            )
            db.commit()
            db.refresh(document)
            return self._document_response(db, document)
        except Exception:
            db.rollback()
            try:
                self.storage.remove(stored.storage_id)
            except StorageUnavailable:
                pass
            raise

    def list_documents(self, db: Session, institution_id: str, record_id: str) -> list[DocumentResponse]:
        self._record_for_scope(db, institution_id, record_id)
        documents = db.scalars(
            select(FDRDocument)
            .where(FDRDocument.institution_id == institution_id, FDRDocument.fdr_record_id == record_id)
            .order_by(FDRDocument.created_at.desc(), FDRDocument.id.desc())
        ).all()
        return [self._document_response(db, document) for document in documents]

    def list_versions(
        self,
        db: Session,
        institution_id: str,
        record_id: str,
        document_id: str,
    ) -> list[DocumentVersionResponse]:
        self._record_for_scope(db, institution_id, record_id)
        document = db.scalar(
            select(FDRDocument).where(
                FDRDocument.id == document_id,
                FDRDocument.institution_id == institution_id,
                FDRDocument.fdr_record_id == record_id,
            )
        )
        if document is None:
            raise EntityNotFound("Document was not found for this institution and FDR record.")
        versions = db.scalars(
            select(FDRDocumentVersion)
            .where(FDRDocumentVersion.document_id == document.id)
            .order_by(FDRDocumentVersion.version_number.asc())
        ).all()
        return [
            self._version_response(version, db.get(WorkflowConfiguration, version.configuration_id).version)
            for version in versions
        ]

    def check_integrity(
        self,
        db: Session,
        institution_id: str,
        record_id: str,
        document_id: str,
        version_id: str,
        actor_id: str,
    ) -> EvidenceCheckResponse:
        self._record_for_scope(db, institution_id, record_id)
        version = db.scalar(
            select(FDRDocumentVersion)
            .join(FDRDocument, FDRDocument.id == FDRDocumentVersion.document_id)
            .where(
                FDRDocumentVersion.id == version_id,
                FDRDocument.id == document_id,
                FDRDocument.institution_id == institution_id,
                FDRDocument.fdr_record_id == record_id,
            )
        )
        if version is None:
            raise EntityNotFound("Document version was not found for this institution and FDR record.")

        try:
            observed_digest = self.storage.sha256_digest(version.storage_id)
        except (OSError, StorageUnavailable):
            result_status = "INDETERMINATE"
            explanation = "Stored bytes could not be read, so the integrity comparison was not completed."
            result_details = {"recorded_sha256": version.sha256_digest, "observed_sha256": None}
        else:
            result_details = {
                "recorded_sha256": version.sha256_digest,
                "observed_sha256": observed_digest,
            }
            if observed_digest == version.sha256_digest:
                result_status = "PASS"
                explanation = (
                    "Recomputed SHA-256 matches the upload-time digest. This confirms byte consistency only; "
                    "it does not establish document authenticity or validity."
                )
            else:
                result_status = "FAIL"
                explanation = (
                    "Recomputed SHA-256 differs from the upload-time digest. This indicates changed bytes "
                    "relative to the recorded copy, not fraud."
                )

        configuration = db.get(WorkflowConfiguration, version.configuration_id)
        check = EvidenceCheck(
            institution_id=institution_id,
            fdr_record_id=record_id,
            document_version_id=version.id,
            check_type="sha256_integrity",
            result_status=result_status,
            explanation=explanation,
            software_version=INTEGRITY_SOFTWARE_VERSION,
            rule_version=version.upload_policy_version,
            evidence_references=[f"document-version:{version.id}"],
            result_details=result_details,
        )
        try:
            db.add(check)
            db.flush()
            db.add(
                AuditEvent(
                    institution_id=institution_id,
                    fdr_record_id=record_id,
                    event_type="document_integrity_checked",
                    actor_id=actor_id,
                    configuration_version=configuration.version,
                    details={
                        "check_type": check.check_type,
                        "result_status": check.result_status,
                        "document_id": document_id,
                        "document_version_id": version.id,
                        "evidence_check_id": check.id,
                    },
                )
            )
            db.commit()
            db.refresh(check)
            return EvidenceCheckResponse.model_validate(check, from_attributes=True)
        except Exception:
            db.rollback()
            raise

    def list_evidence_checks(
        self,
        db: Session,
        institution_id: str,
        record_id: str,
        limit: int,
    ) -> list[EvidenceCheckResponse]:
        self._record_for_scope(db, institution_id, record_id)
        checks = db.scalars(
            select(EvidenceCheck)
            .where(EvidenceCheck.institution_id == institution_id, EvidenceCheck.fdr_record_id == record_id)
            .order_by(EvidenceCheck.executed_at.desc(), EvidenceCheck.id.desc())
            .limit(limit)
        ).all()
        return [EvidenceCheckResponse.model_validate(check, from_attributes=True) for check in checks]
