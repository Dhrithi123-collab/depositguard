import hashlib

from app.models import AuditEvent, EvidenceCheck, FDRDocument, FDRDocumentVersion, FDRRelationship, ReviewPriorityCalculation


SYNTHETIC_PDF = b"%PDF-1.4\nsynthetic integration fixture\n%%EOF\n"


def test_end_to_end_institution_record_upload_integrity_evidence_priority_and_graph(upload_client):
    client, session_factory, storage, _ = upload_client

    created_institution = client.post(
        "/api/institutions",
        json={"name": "Synthetic Integration Institute", "actor_id": "integration-operator"},
    )
    assert created_institution.status_code == 201
    institution_id = created_institution.json()["id"]
    assert institution_id
    institution_list = client.get("/api/institutions")
    assert institution_list.status_code == 200
    assert any(item["id"] == institution_id for item in institution_list.json())
    assert client.get("/api/institutions/missing-integration-institution/fdr-records").status_code == 404
    empty_summary = client.get(f"/api/institutions/{institution_id}/dashboard-summary")
    assert empty_summary.status_code == 200
    assert empty_summary.json()["total_records"] == 0
    assert empty_summary.json()["stage_counts"] == {}
    assert empty_summary.json()["recent_activity"][0]["event_type"] == "institution_created"
    assert client.get("/api/institutions/missing-integration-institution/dashboard-summary").status_code == 404
    graph_policy = client.get("/api/graph/policy")
    assert graph_policy.status_code == 200
    assert any(item["key"] == "related_to" for item in graph_policy.json()["policy"]["relationship_types"])

    first_create = client.post(
        f"/api/institutions/{institution_id}/fdr-records",
        json={"instrument_reference": "SYNTHETIC-E2E-001", "actor_id": "integration-operator"},
    )
    second_create = client.post(
        f"/api/institutions/{institution_id}/fdr-records",
        json={"instrument_reference": "SYNTHETIC-E2E-002", "actor_id": "integration-operator"},
    )
    assert first_create.status_code == second_create.status_code == 201
    record_id = first_create.json()["id"]
    record_list = client.get(f"/api/institutions/{institution_id}/fdr-records")
    assert record_list.status_code == 200
    assert {item["id"] for item in record_list.json()} == {record_id, second_create.json()["id"]}
    assert client.get(f"/api/institutions/missing-integration-institution/fdr-records/{record_id}").status_code == 404

    transition = client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/transitions",
        json={"target_stage": "submitted", "actor_id": "integration-operator"},
    )
    assert transition.status_code == 200
    upload = client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/documents",
        data={"category_key": "illustrative_supporting_evidence", "actor_id": "integration-operator"},
        files={"file": ("synthetic-evidence.pdf", SYNTHETIC_PDF, "application/pdf")},
    )
    assert upload.status_code == 201
    document = upload.json()
    version = document["latest_version"]
    assert version["sha256_digest"] == hashlib.sha256(SYNTHETIC_PDF).hexdigest()
    assert "storage_id" not in version and str(storage.root) not in upload.text

    checked = client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/documents/{document['id']}/versions/{version['id']}/integrity-checks",
        json={"actor_id": "integration-reviewer"},
    )
    assert checked.status_code == 201
    assert checked.json()["result_status"] == "PASS"
    evidence = client.get(f"/api/institutions/{institution_id}/fdr-records/{record_id}/evidence-checks")
    assert evidence.status_code == 200
    assert evidence.json()[0]["id"] == checked.json()["id"]
    assert evidence.json()[0]["document_version_id"] == version["id"]

    summary_response = client.get(f"/api/institutions/{institution_id}/dashboard-summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["institution_id"] == institution_id
    assert summary["total_records"] == 2
    assert summary["stage_counts"] == {"submitted": 1, "draft": 1}
    assert summary["document_count"] == 1
    assert summary["integrity_check_counts"] == {"PASS": 1}
    assert any(event["event_type"] == "document_integrity_checked" and event["fdr_record_id"] == record_id for event in summary["recent_activity"])

    score = client.get(f"/api/institutions/{institution_id}/fdr-records/{record_id}/urgency-score")
    queue = client.get(f"/api/institutions/{institution_id}/review-priority-queue")
    assert score.status_code == queue.status_code == 200
    assert score.json()["record_id"] == record_id
    assert score.json()["policy_version"] == queue.json()["policy_version"]
    assert any(item["record_id"] == record_id for item in queue.json()["items"])

    related = client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/relationships",
        json={
            "target_record_id": second_create.json()["id"],
            "relationship_type": "related_to",
            "review_status": "requires_review",
            "note": "Synthetic integration association",
            "actor_id": "integration-reviewer",
        },
    )
    assert related.status_code == 201
    relationships = client.get(f"/api/institutions/{institution_id}/fdr-records/{record_id}/relationships")
    graph = client.get(f"/api/institutions/{institution_id}/fdr-records/{record_id}/graph?algorithm=BFS")
    assert relationships.status_code == graph.status_code == 200
    assert relationships.json()[0]["relationship_type"] == "related_to"
    assert any(node["entity_id"] == second_create.json()["id"] for node in graph.json()["nodes"])
    assert any(node["entity_type"] == "evidence_check" and node["entity_id"] == checked.json()["id"] for node in graph.json()["nodes"])

    audit = client.get(f"/api/institutions/{institution_id}/fdr-records/{record_id}/audit-events")
    assert audit.status_code == 200
    assert {item["event_type"] for item in audit.json()} >= {
        "record_created", "workflow_transition", "document_uploaded", "document_integrity_checked", "fdr_relationship_recorded",
    }
    with session_factory() as session:
        assert session.query(FDRDocument).filter_by(id=document["id"]).count() == 1
        assert session.query(FDRDocumentVersion).filter_by(id=version["id"]).count() == 1
        assert session.query(EvidenceCheck).filter_by(id=checked.json()["id"]).count() == 1
        assert session.query(FDRRelationship).filter_by(id=related.json()["id"]).count() == 1
        assert session.query(ReviewPriorityCalculation).filter_by(fdr_record_id=record_id).count() >= 1
        assert session.query(AuditEvent).filter_by(fdr_record_id=record_id).count() >= 4
