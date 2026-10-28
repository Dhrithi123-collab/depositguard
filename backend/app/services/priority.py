import hashlib
import heapq
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EvidenceCheck,
    FDRDocument,
    FDRDocumentVersion,
    FDRRecord,
    Institution,
    ReviewPriorityCalculation,
)
from app.schemas.priority import (
    FactorContribution,
    PriorityPolicy,
    PriorityPolicyResponse,
    PriorityQueueItem,
    PriorityQueueResponse,
    UrgencyScoreResponse,
)
from app.services.workflow import EntityNotFound, WorkflowConfigurationError, WorkflowService


NO_DEADLINE_INPUT = "No deadline field is stored for this record; deadline urgency was not evaluated."


class PriorityConfigurationError(Exception):
    pass


class PriorityScoringService:
    def __init__(self, policy_path: Path, workflow: WorkflowService):
        self.policy_path = policy_path
        self.workflow = workflow

    def load_policy(self) -> PriorityPolicy:
        try:
            return PriorityPolicy.model_validate_json(self.policy_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise PriorityConfigurationError("Priority policy is unavailable or invalid.") from exc

    @staticmethod
    def policy_digest(policy: PriorityPolicy) -> str:
        canonical = json.dumps(policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def _workflow_definition(self):
        try:
            return self.workflow.load_configuration()
        except WorkflowConfigurationError as exc:
            raise PriorityConfigurationError("Workflow configuration is unavailable; priority was not calculated.") from exc

    @staticmethod
    def _validate_stage_references(policy: PriorityPolicy, workflow_stages: set[str]) -> None:
        referenced = (
            set(policy.eligible_stages)
            | set(policy.factors.review_wait.eligible_stages)
            | set(policy.factors.outstanding_clarification.stages)
        )
        if not referenced.issubset(workflow_stages):
            raise PriorityConfigurationError("Priority policy references a stage missing from workflow configuration.")

    @staticmethod
    def _assert_policy_version_immutable(db: Session, policy: PriorityPolicy, digest: str) -> None:
        prior_digest = db.scalar(select(ReviewPriorityCalculation.policy_digest).where(
            ReviewPriorityCalculation.policy_version == policy.version,
        ).limit(1))
        if prior_digest is not None and prior_digest != digest:
            raise PriorityConfigurationError("Priority policy version is immutable; use a new version for changed content.")

    @staticmethod
    def _record(db: Session, institution_id: str, record_id: str) -> FDRRecord:
        record = db.scalar(select(FDRRecord).where(
            FDRRecord.id == record_id,
            FDRRecord.institution_id == institution_id,
        ))
        if record is None:
            raise EntityNotFound("FDR record was not found for this institution.")
        return record

    def policy_response(self, db: Session) -> PriorityPolicyResponse:
        policy = self.load_policy()
        workflow_definition = self._workflow_definition()
        self._validate_stage_references(policy, {stage.key for stage in workflow_definition.stages})
        digest = self.policy_digest(policy)
        self._assert_policy_version_immutable(db, policy, digest)
        return PriorityPolicyResponse(policy=policy, policy_digest=digest)

    def calculate_record(
        self, db: Session, institution_id: str, record_id: str,
    ) -> UrgencyScoreResponse:
        policy = self.load_policy()
        workflow_definition = self._workflow_definition()
        self._validate_stage_references(policy, {stage.key for stage in workflow_definition.stages})
        digest = self.policy_digest(policy)
        self._assert_policy_version_immutable(db, policy, digest)
        record = self._record(db, institution_id, record_id)
        result = self._calculate(
            db, record, institution_id, policy, digest,
            workflow_definition.version, workflow_definition, datetime.now(timezone.utc),
        )
        try:
            self._persist(db, result)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return result

    def priority_queue(
        self, db: Session, institution_id: str, limit: int = 100,
    ) -> PriorityQueueResponse:
        policy = self.load_policy()
        workflow_definition = self._workflow_definition()
        self._validate_stage_references(policy, {stage.key for stage in workflow_definition.stages})
        digest = self.policy_digest(policy)
        self._assert_policy_version_immutable(db, policy, digest)
        if db.get(Institution, institution_id) is None:
            raise EntityNotFound("Institution was not found.")
        records = db.scalars(select(FDRRecord).where(
            FDRRecord.institution_id == institution_id,
            FDRRecord.workflow_stage.in_(policy.eligible_stages),
        ).order_by(FDRRecord.id).distinct()).all()
        now = datetime.now(timezone.utc)
        seen: set[str] = set()
        heap: list[tuple[int, float, float, str, PriorityQueueItem]] = []
        calculations: list[PriorityQueueItem] = []
        for record in records:
            if record.id in seen:
                continue
            seen.add(record.id)
            result = self._calculate(
                db, record, institution_id, policy, digest,
                workflow_definition.version, workflow_definition, now,
            )
            item = PriorityQueueItem(
                **result.model_dump(),
                workflow_stage=record.workflow_stage,
                updated_at=record.updated_at,
                relevant_deadline=None,
            )
            updated = self._utc(record.updated_at).timestamp()
            created = self._utc(record.created_at).timestamp()
            heapq.heappush(heap, (-item.score, updated, created, record.id, item))
            calculations.append(item)

        ordered: list[PriorityQueueItem] = []
        while heap and len(ordered) < limit:
            ordered.append(heapq.heappop(heap)[-1])
        try:
            for item in calculations:
                self._persist(db, item)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return PriorityQueueResponse(
            institution_id=institution_id,
            policy_version=policy.version,
            policy_digest=digest,
            calculated_at=now,
            items=ordered,
        )

    def _calculate(
        self, db: Session, record: FDRRecord, institution_id: str,
        policy: PriorityPolicy, digest: str, workflow_version: str,
        workflow_definition, now: datetime,
    ) -> UrgencyScoreResponse:
        factors = policy.factors
        contributions: list[FactorContribution] = []
        missing_inputs = [NO_DEADLINE_INPUT]

        doc_factor = factors.missing_required_documents
        if not doc_factor.enabled:
            contributions.append(FactorContribution(
                factor="missing_required_documents", points=0, evaluated=False,
                explanation="Disabled by the active priority policy.", missing_inputs=[],
            ))
        else:
            required = {item.key for item in workflow_definition.document_requirements if item.required}
            uploaded = set(db.scalars(select(FDRDocument.category_key).where(
                FDRDocument.institution_id == institution_id,
                FDRDocument.fdr_record_id == record.id,
            )).all())
            missing = sorted(required - uploaded)
            points = min(len(missing) * doc_factor.points_per_missing_document, doc_factor.max_points)
            if missing:
                explanation = f"{len(missing)} configured required document category/categories are missing: {', '.join(missing)}."
            elif required:
                explanation = "All currently configured required document categories have at least one uploaded document."
            else:
                explanation = "No required document categories are configured; none were scored."
            contributions.append(FactorContribution(
                factor="missing_required_documents", points=points, evaluated=True,
                explanation=explanation, missing_inputs=[],
            ))

        evidence_factor = factors.evidence_attention
        if not evidence_factor.enabled:
            contributions.append(FactorContribution(
                factor="evidence_attention", points=0, evaluated=False,
                explanation="Disabled by the active priority policy.", missing_inputs=[],
            ))
        else:
            checks = db.scalars(select(EvidenceCheck).where(
                EvidenceCheck.institution_id == institution_id,
                EvidenceCheck.fdr_record_id == record.id,
                EvidenceCheck.check_type == "sha256_integrity",
                EvidenceCheck.document_version_id.is_not(None),
            ).order_by(EvidenceCheck.executed_at.desc(), EvidenceCheck.id.desc())).all()
            latest_by_version: dict[str, EvidenceCheck] = {}
            for check in checks:
                latest_by_version.setdefault(check.document_version_id, check)
            version_ids = set(db.scalars(
                select(FDRDocumentVersion.id)
                .join(FDRDocument, FDRDocument.id == FDRDocumentVersion.document_id)
                .where(
                    FDRDocument.institution_id == institution_id,
                    FDRDocument.fdr_record_id == record.id,
                )
            ).all())
            unchecked_versions = version_ids - set(latest_by_version)
            status_counts: dict[str, int] = {"FAIL": 0, "INDETERMINATE": 0}
            for check in latest_by_version.values():
                if check.result_status in status_counts:
                    status_counts[check.result_status] += 1
            evidence_missing: list[str] = []
            if not latest_by_version:
                points = evidence_factor.points_if_no_checks * max(1, len(version_ids))
                evidence_missing.append("No SHA-256 integrity checks are recorded; this is not treated as a passed check.")
                evidence_explanation = "No integrity checks are recorded; the policy's explicit no-check contribution was applied."
                missing_inputs.extend(evidence_missing)
            else:
                points = sum(count * evidence_factor.points_by_status[status] for status, count in status_counts.items())
                points += len(unchecked_versions) * evidence_factor.points_if_no_checks
                if unchecked_versions:
                    evidence_missing.append(
                        f"{len(unchecked_versions)} document version(s) have no SHA-256 integrity check recorded."
                    )
                    missing_inputs.extend(evidence_missing)
                points = min(points, evidence_factor.max_points)
                evidence_explanation = (
                    f"Latest checks per version: {status_counts['FAIL']} FAIL and "
                    f"{status_counts['INDETERMINATE']} INDETERMINATE; {len(unchecked_versions)} version(s) unchecked; "
                    "PASS results do not add urgency points."
                )
            points = min(points, evidence_factor.max_points)
            contributions.append(FactorContribution(
                factor="evidence_attention", points=points, evaluated=bool(latest_by_version),
                explanation=evidence_explanation, missing_inputs=evidence_missing,
            ))

        clarification_factor = factors.outstanding_clarification
        if not clarification_factor.enabled:
            clarification_points = 0
            clarification_explanation = "Disabled by the active priority policy."
        elif record.workflow_stage in clarification_factor.stages:
            clarification_points = clarification_factor.points
            clarification_explanation = "The record is in a configured clarification stage."
        else:
            clarification_points = 0
            clarification_explanation = "The current workflow stage is not configured as outstanding clarification."
        contributions.append(FactorContribution(
            factor="outstanding_clarification", points=clarification_points,
            evaluated=clarification_factor.enabled, explanation=clarification_explanation,
            missing_inputs=[],
        ))

        wait_factor = factors.review_wait
        if not wait_factor.enabled:
            wait_points = 0
            wait_explanation = "Disabled by the active priority policy."
            wait_evaluated = False
        elif record.workflow_stage not in wait_factor.eligible_stages:
            wait_points = 0
            wait_explanation = "The current stage is not configured for review-wait scoring."
            wait_evaluated = True
        else:
            elapsed_days = max(0, int((now - self._utc(record.updated_at)).total_seconds() // 86400))
            chargeable_days = max(0, elapsed_days - wait_factor.minimum_wait_days)
            wait_points = min(chargeable_days * wait_factor.points_per_day_after_threshold, wait_factor.max_points)
            wait_explanation = (
                f"In the current workflow stage for {elapsed_days} day(s); "
                f"{chargeable_days} day(s) count after the configured waiting threshold."
            )
            wait_evaluated = True
        contributions.append(FactorContribution(
            factor="review_wait", points=wait_points, evaluated=wait_evaluated,
            explanation=wait_explanation, missing_inputs=[],
        ))

        score = min(100, sum(factor.points for factor in contributions))
        category = max(
            (item for item in policy.categories if item.minimum_score <= score),
            key=lambda item: item.minimum_score,
        )
        return UrgencyScoreResponse(
            calculation_id="pending",
            institution_id=institution_id,
            record_id=record.id,
            score=score,
            priority_category_key=category.key,
            priority_category_label=category.label,
            policy_version=policy.version,
            policy_digest=digest,
            workflow_config_version=workflow_version,
            calculated_at=now,
            factors=contributions,
            missing_inputs=missing_inputs,
        )

    @staticmethod
    def _persist(db: Session, result: UrgencyScoreResponse) -> None:
        row = ReviewPriorityCalculation(
            institution_id=result.institution_id,
            fdr_record_id=result.record_id,
            score=result.score,
            priority_category_key=result.priority_category_key,
            priority_category_label=result.priority_category_label,
            policy_version=result.policy_version,
            policy_digest=result.policy_digest,
            workflow_config_version=result.workflow_config_version,
            factors=[item.model_dump(mode="json") for item in result.factors],
            missing_inputs=result.missing_inputs,
            calculated_at=result.calculated_at,
        )
        db.add(row)
        db.flush()
        result.calculation_id = row.id
