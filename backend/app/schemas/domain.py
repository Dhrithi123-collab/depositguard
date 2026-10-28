from datetime import datetime

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.workflow import WorkflowDefinition

InstitutionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ActorId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
InstrumentReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TransitionStage = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=1, max_length=80)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class InstitutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: InstitutionName
    actor_id: ActorId


class InstitutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime


class FDRRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_reference: InstrumentReference | None = None
    actor_id: ActorId


class FDRRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    institution_id: str
    instrument_reference: str | None
    workflow_stage: str
    created_at: datetime
    updated_at: datetime


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_stage: TransitionStage
    actor_id: ActorId
    reason: Reason | None = None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    institution_id: str
    fdr_record_id: str | None
    event_type: str
    actor_id: str
    configuration_version: str | None
    from_stage: str | None
    to_stage: str | None
    reason: str | None
    details: dict
    created_at: datetime


class DashboardSummaryResponse(BaseModel):
    institution_id: str
    total_records: int
    stage_counts: dict[str, int]
    document_count: int
    integrity_check_counts: dict[str, int]
    recent_activity: list[AuditEventResponse]


class WorkflowConfigurationResponse(BaseModel):
    config: WorkflowDefinition
