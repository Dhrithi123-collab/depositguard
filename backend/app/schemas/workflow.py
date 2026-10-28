from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

StageKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")]
RequirementKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")]
Version = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class WorkflowStageConfig(BaseModel):
    key: StageKey
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class WorkflowTransitionConfig(BaseModel):
    from_stage: StageKey
    to_stage: StageKey


class DocumentRequirementConfig(BaseModel):
    key: RequirementKey
    label: Label
    required: bool


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Version
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    initial_stage: StageKey
    stages: list[WorkflowStageConfig] = Field(min_length=1)
    transitions: list[WorkflowTransitionConfig]
    decision_stages: list[StageKey] = Field(default_factory=list)
    clarification_stages: list[StageKey] = Field(default_factory=list)
    document_requirements: list[DocumentRequirementConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references_and_duplicates(self) -> "WorkflowDefinition":
        stage_keys = [stage.key for stage in self.stages]
        if len(stage_keys) != len(set(stage_keys)):
            raise ValueError("Workflow stage keys must be unique.")
        stage_set = set(stage_keys)
        if self.initial_stage not in stage_set:
            raise ValueError("The initial stage must be declared in stages.")

        transition_pairs = [(item.from_stage, item.to_stage) for item in self.transitions]
        if len(transition_pairs) != len(set(transition_pairs)):
            raise ValueError("Workflow transitions must be unique.")
        for from_stage, to_stage in transition_pairs:
            if from_stage not in stage_set or to_stage not in stage_set:
                raise ValueError("Every transition must refer to declared stages.")
            if from_stage == to_stage:
                raise ValueError("Self-transitions are not permitted.")

        if not set(self.decision_stages).issubset(stage_set) or len(self.decision_stages) != len(set(self.decision_stages)):
            raise ValueError("Decision stages must be unique declared workflow stages.")
        if not set(self.clarification_stages).issubset(stage_set) or len(self.clarification_stages) != len(set(self.clarification_stages)):
            raise ValueError("Clarification stages must be unique declared workflow stages.")
        if set(self.decision_stages) & set(self.clarification_stages):
            raise ValueError("A workflow stage cannot be both a decision and clarification stage.")

        requirement_keys = [item.key for item in self.document_requirements]
        if len(requirement_keys) != len(set(requirement_keys)):
            raise ValueError("Document requirement keys must be unique.")
        return self
