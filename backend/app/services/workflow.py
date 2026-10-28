import hashlib
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, DocumentRequirement, FDRRecord, Institution, WorkflowConfiguration
from app.schemas.workflow import WorkflowDefinition


class WorkflowConfigurationError(Exception):
    """Configuration was missing, malformed, or reused an immutable version ID."""


class EntityNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


class WorkflowService:
    def __init__(self, config_path: Path):
        self.config_path = config_path

    def load_configuration(self) -> WorkflowDefinition:
        path = self.config_path
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            raw = path.read_text(encoding="utf-8")
            return WorkflowDefinition.model_validate_json(raw)
        except (OSError, ValidationError, ValueError) as exc:
            raise WorkflowConfigurationError(
                "Workflow configuration is unavailable or invalid; no transition was applied."
            ) from exc

    @staticmethod
    def _definition_digest(config: WorkflowDefinition) -> tuple[dict, str]:
        definition = config.model_dump(mode="json")
        canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return definition, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def store_configuration(self, db: Session, config: WorkflowDefinition) -> WorkflowConfiguration:
        definition, digest = self._definition_digest(config)
        existing = db.scalar(select(WorkflowConfiguration).where(WorkflowConfiguration.version == config.version))
        if existing:
            if existing.content_hash != digest:
                raise WorkflowConfigurationError(
                    "Workflow configuration version is immutable; use a new version value for changed content."
                )
            return existing

        snapshot = WorkflowConfiguration(version=config.version, content_hash=digest, definition=definition)
        db.add(snapshot)
        db.flush()
        db.add_all(
            DocumentRequirement(
                configuration_id=snapshot.id,
                requirement_key=requirement.key,
                label=requirement.label,
                required=requirement.required,
            )
            for requirement in config.document_requirements
        )
        return snapshot

    @staticmethod
    def _commit(db: Session) -> None:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    def create_record(
        self,
        db: Session,
        institution_id: str,
        instrument_reference: str | None,
        actor_id: str,
    ) -> FDRRecord:
        institution = db.scalar(select(Institution).where(Institution.id == institution_id))
        if institution is None:
            raise EntityNotFound("Institution was not found.")
        config = self.load_configuration()
        try:
            snapshot = self.store_configuration(db, config)
            record = FDRRecord(
                institution_id=institution.id,
                instrument_reference=instrument_reference,
                workflow_stage=config.initial_stage,
            )
            db.add(record)
            db.flush()
            db.add(
                AuditEvent(
                    institution_id=institution.id,
                    fdr_record_id=record.id,
                    event_type="record_created",
                    actor_id=actor_id,
                    configuration_version=snapshot.version,
                    to_stage=config.initial_stage,
                    details={"workflow_stage": config.initial_stage},
                )
            )
            self._commit(db)
            db.refresh(record)
            return record
        except Exception:
            db.rollback()
            raise

    def transition(
        self,
        db: Session,
        institution_id: str,
        record_id: str,
        target_stage: str,
        actor_id: str,
        reason: str | None,
    ) -> FDRRecord:
        record = db.scalar(
            select(FDRRecord).where(
                FDRRecord.id == record_id,
                FDRRecord.institution_id == institution_id,
            )
        )
        if record is None:
            raise EntityNotFound("FDR record was not found for this institution.")
        config = self.load_configuration()
        try:
            snapshot = self.store_configuration(db, config)
            allowed = any(
                item.from_stage == record.workflow_stage and item.to_stage == target_stage
                for item in config.transitions
            )
            if not allowed:
                db.add(
                    AuditEvent(
                        institution_id=institution_id,
                        fdr_record_id=record.id,
                        event_type="workflow_transition_rejected",
                        actor_id=actor_id,
                        configuration_version=snapshot.version,
                        from_stage=record.workflow_stage,
                        to_stage=target_stage,
                        reason=reason,
                        details={"outcome": "rejected"},
                    )
                )
                self._commit(db)
                raise InvalidTransition(
                    f"Transition from '{record.workflow_stage}' to '{target_stage}' is not allowed by configuration '{config.version}'."
                )

            previous_stage = record.workflow_stage
            record.workflow_stage = target_stage
            db.add(
                AuditEvent(
                    institution_id=institution_id,
                    fdr_record_id=record.id,
                    event_type="workflow_transition",
                    actor_id=actor_id,
                    configuration_version=snapshot.version,
                    from_stage=previous_stage,
                    to_stage=target_stage,
                    reason=reason,
                    details={"outcome": "accepted"},
                )
            )
            self._commit(db)
            db.refresh(record)
            return record
        except InvalidTransition:
            raise
        except Exception:
            db.rollback()
            raise
