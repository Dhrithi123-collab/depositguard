from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


PolicyVersion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
CategoryKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")]
PolicyLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Points = Annotated[int, Field(ge=0, le=100)]


class MissingDocumentsFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    points_per_missing_document: Points
    max_points: Points


class EvidenceAttentionFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    points_by_status: dict[Literal["FAIL", "INDETERMINATE"], Points]
    points_if_no_checks: Points
    max_points: Points

    @model_validator(mode="after")
    def require_both_statuses(self) -> "EvidenceAttentionFactor":
        if set(self.points_by_status) != {"FAIL", "INDETERMINATE"}:
            raise ValueError("Evidence attention must define FAIL and INDETERMINATE point values.")
        return self


class ClarificationFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    stages: list[CategoryKey]
    points: Points


class ReviewWaitFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    eligible_stages: list[CategoryKey]
    minimum_wait_days: int = Field(ge=0, le=3650)
    points_per_day_after_threshold: Points
    max_points: Points


class PriorityFactors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_required_documents: MissingDocumentsFactor
    evidence_attention: EvidenceAttentionFactor
    outstanding_clarification: ClarificationFactor
    review_wait: ReviewWaitFactor


class PriorityCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: CategoryKey
    label: PolicyLabel
    minimum_score: int = Field(ge=0, le=100)


class PriorityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: PolicyVersion
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    eligible_stages: list[CategoryKey] = Field(min_length=1)
    factors: PriorityFactors
    categories: list[PriorityCategory] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy_order_and_stage_sets(self) -> "PriorityPolicy":
        keys = [item.key for item in self.categories]
        thresholds = [item.minimum_score for item in self.categories]
        if len(keys) != len(set(keys)):
            raise ValueError("Priority category keys must be unique.")
        if thresholds[0] != 0 or thresholds != sorted(set(thresholds)):
            raise ValueError("Priority categories must have unique ascending thresholds beginning at zero.")
        if len(self.eligible_stages) != len(set(self.eligible_stages)):
            raise ValueError("Eligible workflow stages must be unique.")
        if len(self.factors.review_wait.eligible_stages) != len(set(self.factors.review_wait.eligible_stages)):
            raise ValueError("Review wait stages must be unique.")
        if len(self.factors.outstanding_clarification.stages) != len(set(self.factors.outstanding_clarification.stages)):
            raise ValueError("Clarification stages must be unique.")
        if not set(self.factors.review_wait.eligible_stages).issubset(self.eligible_stages):
            raise ValueError("Review wait stages must also be eligible queue stages.")
        return self


class FactorContribution(BaseModel):
    factor: str
    points: int
    evaluated: bool
    explanation: str
    missing_inputs: list[str]


class UrgencyScoreResponse(BaseModel):
    calculation_id: str
    institution_id: str
    record_id: str
    score: int
    priority_category_key: str
    priority_category_label: str
    policy_version: str
    policy_digest: str
    workflow_config_version: str
    calculated_at: datetime
    factors: list[FactorContribution]
    missing_inputs: list[str]


class PriorityQueueItem(UrgencyScoreResponse):
    workflow_stage: str
    updated_at: datetime
    relevant_deadline: datetime | None = None


class PriorityQueueResponse(BaseModel):
    institution_id: str
    policy_version: str
    policy_digest: str
    calculated_at: datetime
    items: list[PriorityQueueItem]


class PriorityPolicyResponse(BaseModel):
    policy: PriorityPolicy
    policy_digest: str
