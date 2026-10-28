from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.domain import ActorId


RelationshipKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")]
GraphEntityType = Literal["fdr_record", "document", "document_version", "evidence_check", "audit_event"]


class RelationshipTypeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: RelationshipKey
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    allow_cycles: bool


class GraphPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    max_traversal_depth: int = Field(ge=1, le=12)
    max_nodes: int = Field(default=500, ge=1, le=2000)
    relationship_types: list[RelationshipTypeConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_relationship_types(self) -> "GraphPolicy":
        keys = [item.key for item in self.relationship_types]
        if len(keys) != len(set(keys)):
            raise ValueError("Relationship type keys must be unique.")
        return self


class GraphPolicyResponse(BaseModel):
    policy: GraphPolicy


class RelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_record_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=36)]
    relationship_type: RelationshipKey
    review_status: Literal["unreviewed", "requires_review"] = "unreviewed"
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    actor_id: ActorId


class RelationshipResponse(BaseModel):
    id: str
    institution_id: str
    source_record_id: str
    target_record_id: str
    relationship_type: str
    relationship_label: str
    review_status: str
    note: str | None
    created_by: str
    created_at: datetime


class GraphNode(BaseModel):
    entity_type: GraphEntityType
    entity_id: str
    institution_id: str
    label: str
    depth: int


class GraphEdge(BaseModel):
    edge_id: str
    source: GraphEntityType
    source_id: str
    target: GraphEntityType
    target_id: str
    relationship_type: str
    relationship_label: str
    review_status: str | None = None
    traversal_depth: int


class TraversalResponse(BaseModel):
    algorithm: Literal["BFS", "DFS"]
    start_node: GraphNode
    max_depth: int
    max_nodes: int
    truncated: bool
    nodes: list[GraphNode]
    edges: list[GraphEdge]
