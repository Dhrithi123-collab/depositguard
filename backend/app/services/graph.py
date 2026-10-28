from collections import deque
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditEvent, EvidenceCheck, FDRDocument, FDRDocumentVersion, FDRRecord, FDRRelationship
from app.schemas.graph import GraphEdge, GraphNode, GraphPolicy, GraphPolicyResponse, RelationshipResponse, TraversalResponse
from app.services.workflow import EntityNotFound


class GraphPolicyError(Exception):
    pass


class InvalidRelationship(Exception):
    pass


class RelationshipConflict(Exception):
    pass


class GraphService:
    STRUCTURAL_LABELS = {
        "has_document": "Supporting document",
        "has_version": "Document version",
        "has_integrity_check": "Integrity check",
        "has_evidence_check": "Evidence check",
        "has_lifecycle_event": "Lifecycle event",
    }

    def __init__(self, policy_path: Path):
        self.policy_path = policy_path

    def load_policy(self) -> GraphPolicy:
        try:
            import json

            return GraphPolicy.model_validate_json(self.policy_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise GraphPolicyError("Graph policy is unavailable or invalid.") from exc

    def policy_response(self) -> GraphPolicyResponse:
        return GraphPolicyResponse(policy=self.load_policy())

    @staticmethod
    def _record(db: Session, institution_id: str, record_id: str) -> FDRRecord:
        record = db.scalar(select(FDRRecord).where(
            FDRRecord.id == record_id, FDRRecord.institution_id == institution_id,
        ))
        if record is None:
            raise EntityNotFound("FDR record was not found for this institution.")
        return record

    @staticmethod
    def _relationship_response(row: FDRRelationship, policy: GraphPolicy) -> RelationshipResponse:
        type_config = next((item for item in policy.relationship_types if item.key == row.relationship_type), None)
        return RelationshipResponse(
            id=row.id, institution_id=row.institution_id,
            source_record_id=row.source_record_id, target_record_id=row.target_record_id,
            relationship_type=row.relationship_type,
            relationship_label=type_config.label if type_config else row.relationship_type.replace("_", " ").title(),
            review_status=row.review_status, note=row.note, created_by=row.created_by,
            created_at=row.created_at,
        )

    def create_relationship(
        self, db: Session, institution_id: str, source_record_id: str,
        target_record_id: str, relationship_type: str, review_status: str,
        note: str | None, actor_id: str,
    ) -> RelationshipResponse:
        policy = self.load_policy()
        configured = next((item for item in policy.relationship_types if item.key == relationship_type), None)
        if configured is None:
            raise InvalidRelationship("Relationship type is not allowed by the active graph policy.")
        source = self._record(db, institution_id, source_record_id)
        target = self._record(db, institution_id, target_record_id)
        if source.id == target.id:
            raise InvalidRelationship("An FDR record cannot be related to itself.")
        duplicate = db.scalar(select(FDRRelationship.id).where(
            FDRRelationship.institution_id == institution_id,
            FDRRelationship.source_record_id == source.id,
            FDRRelationship.target_record_id == target.id,
            FDRRelationship.relationship_type == relationship_type,
        ))
        if duplicate is not None:
            raise RelationshipConflict("This relationship has already been recorded.")

        if not configured.allow_cycles and self._directed_path_exists(
            db, institution_id, relationship_type, target.id, source.id,
        ):
            raise InvalidRelationship("This relationship would create a prohibited cycle.")

        row = FDRRelationship(
            institution_id=institution_id,
            source_record_id=source.id,
            target_record_id=target.id,
            relationship_type=relationship_type,
            review_status=review_status,
            note=note,
            created_by=actor_id,
        )
        try:
            db.add(row)
            db.flush()
            db.add(AuditEvent(
                institution_id=institution_id,
                fdr_record_id=source.id,
                event_type="fdr_relationship_recorded",
                actor_id=actor_id,
                details={
                    "relationship_id": row.id,
                    "target_record_id": target.id,
                    "relationship_type": relationship_type,
                    "review_status": review_status,
                    "graph_policy_version": policy.version,
                },
            ))
            db.commit()
            db.refresh(row)
            return self._relationship_response(row, policy)
        except IntegrityError as exc:
            db.rollback()
            raise RelationshipConflict("This relationship conflicts with an existing relationship.") from exc
        except Exception:
            db.rollback()
            raise

    def list_relationships(
        self, db: Session, institution_id: str, record_id: str, limit: int = 100,
    ) -> list[RelationshipResponse]:
        policy = self.load_policy()
        self._record(db, institution_id, record_id)
        rows = db.scalars(
            select(FDRRelationship).where(
                FDRRelationship.institution_id == institution_id,
                (FDRRelationship.source_record_id == record_id) | (FDRRelationship.target_record_id == record_id),
            ).order_by(FDRRelationship.created_at, FDRRelationship.id).limit(limit)
        ).all()
        return [self._relationship_response(row, policy) for row in rows]

    @staticmethod
    def _directed_path_exists(
        db: Session, institution_id: str, relationship_type: str, start_id: str, goal_id: str,
    ) -> bool:
        pending = [start_id]
        visited = {start_id}
        while pending:
            current = pending.pop()
            if current == goal_id:
                return True
            targets = db.scalars(select(FDRRelationship.target_record_id).where(
                FDRRelationship.institution_id == institution_id,
                FDRRelationship.relationship_type == relationship_type,
                FDRRelationship.source_record_id == current,
            )).all()
            for target in targets:
                if target not in visited:
                    visited.add(target)
                    pending.append(target)
        return False

    def traverse(
        self, db: Session, institution_id: str, start_record_id: str,
        algorithm: str, max_depth: int | None,
    ) -> TraversalResponse:
        policy = self.load_policy()
        record = self._record(db, institution_id, start_record_id)
        depth_limit = policy.max_traversal_depth if max_depth is None else max_depth
        if depth_limit > policy.max_traversal_depth:
            raise InvalidRelationship("Requested depth exceeds the configured traversal maximum.")
        start = GraphNode(
            entity_type="fdr_record", entity_id=record.id,
            institution_id=institution_id, label="FDR record", depth=0,
        )
        nodes = [start]
        edges: list[GraphEdge] = []
        truncated = False
        visited = {("fdr_record", record.id)}
        if algorithm == "BFS":
            pending = deque([start])
            while pending:
                if truncated:
                    break
                current = pending.popleft()
                if current.depth >= depth_limit:
                    continue
                for neighbor, edge in self._neighbors(db, institution_id, current, policy):
                    key = (neighbor.entity_type, neighbor.entity_id)
                    if key in visited:
                        continue
                    if len(nodes) >= policy.max_nodes:
                        truncated = True
                        break
                    visited.add(key)
                    neighbor.depth = current.depth + 1
                    edge.traversal_depth = neighbor.depth
                    nodes.append(neighbor)
                    edges.append(edge)
                    pending.append(neighbor)
        else:
            frames = [(start, iter(self._neighbors(db, institution_id, start, policy)))]
            while frames and not truncated:
                current, candidates = frames[-1]
                if current.depth >= depth_limit:
                    frames.pop()
                    continue
                try:
                    neighbor, edge = next(candidates)
                except StopIteration:
                    frames.pop()
                    continue
                key = (neighbor.entity_type, neighbor.entity_id)
                if key in visited:
                    continue
                if len(nodes) >= policy.max_nodes:
                    truncated = True
                    break
                visited.add(key)
                neighbor.depth = current.depth + 1
                edge.traversal_depth = neighbor.depth
                nodes.append(neighbor)
                edges.append(edge)
                frames.append((neighbor, iter(self._neighbors(db, institution_id, neighbor, policy))))
        return TraversalResponse(
            algorithm=algorithm,
            start_node=start,
            max_depth=depth_limit,
            max_nodes=policy.max_nodes,
            truncated=truncated,
            nodes=nodes,
            edges=edges,
        )

    def _neighbors(
        self, db: Session, institution_id: str, current: GraphNode, policy: GraphPolicy,
    ) -> list[tuple[GraphNode, GraphEdge]]:
        result: list[tuple[GraphNode, GraphEdge]] = []

        def add(
            target_type: str, target_id: str, target_label: str,
            edge_id: str, edge_type: str, edge_label: str,
            source_type: str, source_id: str, destination_type: str, destination_id: str,
            review_status: str | None = None,
        ) -> None:
            node = GraphNode(
                entity_type=target_type, entity_id=target_id,
                institution_id=institution_id, label=target_label, depth=0,
            )
            edge = GraphEdge(
                edge_id=edge_id,
                source=source_type, source_id=source_id,
                target=destination_type, target_id=destination_id,
                relationship_type=edge_type, relationship_label=edge_label,
                review_status=review_status, traversal_depth=0,
            )
            result.append((node, edge))

        if current.entity_type == "fdr_record":
            explicit = db.scalars(select(FDRRelationship).where(
                FDRRelationship.institution_id == institution_id,
                (FDRRelationship.source_record_id == current.entity_id)
                | (FDRRelationship.target_record_id == current.entity_id),
            )).all()
            configured_types = {item.key: item.label for item in policy.relationship_types}
            for relation in explicit:
                if relation.source_record_id == current.entity_id:
                    other = relation.target_record_id
                else:
                    other = relation.source_record_id
                related = db.scalar(select(FDRRecord).where(
                    FDRRecord.id == other, FDRRecord.institution_id == institution_id,
                ))
                if related is None:
                    continue
                add("fdr_record", related.id, "FDR record", relation.id,
                    relation.relationship_type, configured_types.get(relation.relationship_type, relation.relationship_type),
                    "fdr_record", relation.source_record_id, "fdr_record", relation.target_record_id,
                    relation.review_status)

            documents = db.scalars(select(FDRDocument).where(
                FDRDocument.institution_id == institution_id,
                FDRDocument.fdr_record_id == current.entity_id,
            ).order_by(FDRDocument.id)).all()
            for doc in documents:
                add("document", doc.id, f"Document: {doc.category_key}", f"document:{doc.id}",
                    "has_document", self.STRUCTURAL_LABELS["has_document"],
                    "fdr_record", current.entity_id, "document", doc.id)
            checks = db.scalars(select(EvidenceCheck).where(
                EvidenceCheck.institution_id == institution_id,
                EvidenceCheck.fdr_record_id == current.entity_id,
            ).order_by(EvidenceCheck.executed_at, EvidenceCheck.id)).all()
            for check in checks:
                add("evidence_check", check.id, f"Evidence check: {check.result_status}", f"fdr-evidence:{check.id}",
                    "has_evidence_check", self.STRUCTURAL_LABELS["has_evidence_check"],
                    "fdr_record", current.entity_id, "evidence_check", check.id)
            events = db.scalars(select(AuditEvent).where(
                AuditEvent.institution_id == institution_id,
                AuditEvent.fdr_record_id == current.entity_id,
            ).order_by(AuditEvent.created_at, AuditEvent.id)).all()
            for event in events:
                add("audit_event", event.id, f"Lifecycle event: {event.event_type}", f"audit:{event.id}",
                    "has_lifecycle_event", self.STRUCTURAL_LABELS["has_lifecycle_event"],
                    "fdr_record", current.entity_id, "audit_event", event.id)

        elif current.entity_type == "document":
            doc = db.scalar(select(FDRDocument).where(
                FDRDocument.id == current.entity_id, FDRDocument.institution_id == institution_id,
            ))
            if doc:
                add("fdr_record", doc.fdr_record_id, "FDR record", f"document:{doc.id}",
                    "has_document", self.STRUCTURAL_LABELS["has_document"],
                    "fdr_record", doc.fdr_record_id, "document", doc.id)
                versions = db.scalars(select(FDRDocumentVersion).where(
                    FDRDocumentVersion.document_id == doc.id,
                ).order_by(FDRDocumentVersion.version_number)).all()
                for version in versions:
                    add("document_version", version.id, f"Version {version.version_number}", f"version:{version.id}",
                        "has_version", self.STRUCTURAL_LABELS["has_version"],
                        "document", doc.id, "document_version", version.id)

        elif current.entity_type == "document_version":
            version = db.scalar(select(FDRDocumentVersion).join(
                FDRDocument, FDRDocument.id == FDRDocumentVersion.document_id,
            ).where(
                FDRDocumentVersion.id == current.entity_id,
                FDRDocument.institution_id == institution_id,
            ))
            if version:
                doc = db.get(FDRDocument, version.document_id)
                if doc:
                    add("document", doc.id, f"Document: {doc.category_key}", f"version:{version.id}",
                        "has_version", self.STRUCTURAL_LABELS["has_version"],
                        "document", doc.id, "document_version", version.id)
                    checks = db.scalars(select(EvidenceCheck).where(
                        EvidenceCheck.institution_id == institution_id,
                        EvidenceCheck.document_version_id == version.id,
                    ).order_by(EvidenceCheck.executed_at, EvidenceCheck.id)).all()
                    for check in checks:
                        add("evidence_check", check.id, f"Integrity check: {check.result_status}", f"version-evidence:{check.id}",
                            "has_integrity_check", self.STRUCTURAL_LABELS["has_integrity_check"],
                            "document_version", version.id, "evidence_check", check.id)

        elif current.entity_type == "evidence_check":
            check = db.scalar(select(EvidenceCheck).where(
                EvidenceCheck.id == current.entity_id,
                EvidenceCheck.institution_id == institution_id,
            ))
            if check:
                add("fdr_record", check.fdr_record_id, "FDR record", f"fdr-evidence:{check.id}",
                    "has_evidence_check", self.STRUCTURAL_LABELS["has_evidence_check"],
                    "fdr_record", check.fdr_record_id, "evidence_check", check.id)
                if check.document_version_id:
                    version = db.scalar(select(FDRDocumentVersion).join(
                        FDRDocument, FDRDocument.id == FDRDocumentVersion.document_id,
                    ).where(
                        FDRDocumentVersion.id == check.document_version_id,
                        FDRDocument.institution_id == institution_id,
                    ))
                    if version:
                        add("document_version", version.id, f"Version {version.version_number}", f"version-evidence:{check.id}",
                            "has_integrity_check", self.STRUCTURAL_LABELS["has_integrity_check"],
                            "document_version", version.id, "evidence_check", check.id)

        elif current.entity_type == "audit_event":
            event = db.scalar(select(AuditEvent).where(
                AuditEvent.id == current.entity_id,
                AuditEvent.institution_id == institution_id,
                AuditEvent.fdr_record_id.is_not(None),
            ))
            if event and event.fdr_record_id:
                add("fdr_record", event.fdr_record_id, "FDR record", f"audit:{event.id}",
                    "has_lifecycle_event", self.STRUCTURAL_LABELS["has_lifecycle_event"],
                    "fdr_record", event.fdr_record_id, "audit_event", event.id)

        result.sort(key=lambda item: (
            item[0].entity_type, item[0].entity_id,
            item[1].relationship_type, item[1].edge_id,
        ))
        return result
