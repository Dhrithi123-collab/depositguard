import json

from app.models import AuditEvent, DocumentRequirement, FDRRecord, Institution, WorkflowConfiguration


def create_institution(client):
    response = client.post("/api/institutions", json={"name": "Synthetic Institute A", "actor_id": "prototype-operator"})
    assert response.status_code == 201
    return response.json()


def create_record(client, institution_id: str):
    response = client.post(
        f"/api/institutions/{institution_id}/fdr-records",
        json={"instrument_reference": "SYNTHETIC-REF-001", "actor_id": "prototype-operator"},
    )
    assert response.status_code == 201
    return response.json()


def test_create_institution_records_audit_event(client) -> None:
    test_client, _, session_factory = client

    response = test_client.post("/api/institutions", json={"name": "Synthetic Institute", "actor_id": "tester"})

    assert response.status_code == 201
    assert response.json()["name"] == "Synthetic Institute"
    with session_factory() as session:
        event = session.query(AuditEvent).filter_by(institution_id=response.json()["id"]).one()
        assert event.event_type == "institution_created"
        assert event.actor_id == test_client.get("/api/auth/session").json()["user"]["id"]


def test_create_fdr_record_uses_active_initial_stage_and_snapshots_requirements(client) -> None:
    test_client, _, session_factory = client
    institution = create_institution(test_client)

    record = create_record(test_client, institution["id"])

    assert record["workflow_stage"] == "draft"
    with session_factory() as session:
        config = session.query(WorkflowConfiguration).filter_by(version="prototype-demo-v2").one()
        requirement = session.query(DocumentRequirement).filter_by(configuration_id=config.id).one()
        assert requirement.requirement_key == "illustrative_supporting_evidence"
        assert requirement.required is False
        event = session.query(AuditEvent).filter_by(fdr_record_id=record["id"]).one()
        assert event.event_type == "record_created"
        assert event.configuration_version == "prototype-demo-v2"


def test_read_fdr_record(client) -> None:
    test_client, _, _ = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{record['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == record["id"]
    assert response.json()["institution_id"] == institution["id"]


def test_reject_invalid_transition_and_preserve_stage(client) -> None:
    test_client, _, session_factory = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/transitions",
        json={"target_stage": "completed", "actor_id": "tester", "reason": "Not yet reviewed"},
    )

    assert response.status_code == 409
    assert "not allowed" in response.json()["error"]["message"]
    with session_factory() as session:
        saved_record = session.get(FDRRecord, record["id"])
        rejected_event = session.query(AuditEvent).filter_by(event_type="workflow_transition_rejected").one()
        assert saved_record.workflow_stage == "draft"
        assert rejected_event.from_stage == "draft"
        assert rejected_event.to_stage == "completed"
        assert rejected_event.configuration_version == "prototype-demo-v2"


def test_valid_transition_updates_record_and_records_versioned_audit(client) -> None:
    test_client, _, session_factory = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/transitions",
        json={"target_stage": "submitted", "actor_id": "prototype-reviewer", "reason": "Demo transition"},
    )

    assert response.status_code == 200
    assert response.json()["workflow_stage"] == "submitted"
    history = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/audit-events"
    )
    assert history.status_code == 200
    event = next(item for item in history.json() if item["event_type"] == "workflow_transition")
    assert event["from_stage"] == "draft"
    assert event["to_stage"] == "submitted"
    assert event["configuration_version"] == "prototype-demo-v2"
    with session_factory() as session:
        assert session.get(FDRRecord, record["id"]).workflow_stage == "submitted"


def test_malformed_workflow_configuration_is_rejected(client) -> None:
    test_client, config_path, _ = client
    definition = json.loads(config_path.read_text(encoding="utf-8"))
    definition["transitions"].append({"from_stage": "draft", "to_stage": "not_a_stage"})
    config_path.write_text(json.dumps(definition), encoding="utf-8")

    response = test_client.get("/api/workflow/configuration")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "workflow_configuration_unavailable"


def test_malformed_configuration_fails_closed_without_changing_record(client) -> None:
    test_client, config_path, session_factory = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    definition = json.loads(config_path.read_text(encoding="utf-8"))
    definition["initial_stage"] = "undefined_stage"
    config_path.write_text(json.dumps(definition), encoding="utf-8")

    response = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/transitions",
        json={"target_stage": "submitted", "actor_id": "tester"},
    )

    assert response.status_code == 503
    with session_factory() as session:
        assert session.get(FDRRecord, record["id"]).workflow_stage == "draft"
        assert session.query(AuditEvent).filter_by(event_type="workflow_transition").count() == 0


def test_editing_config_file_changes_allowed_transitions_without_code_change(client) -> None:
    test_client, config_path, session_factory = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    definition = json.loads(config_path.read_text(encoding="utf-8"))
    definition["version"] = "prototype-demo-v3"
    definition["transitions"].append({"from_stage": "draft", "to_stage": "completed"})
    config_path.write_text(json.dumps(definition), encoding="utf-8")

    response = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/transitions",
        json={"target_stage": "completed", "actor_id": "tester"},
    )

    assert response.status_code == 200
    assert response.json()["workflow_stage"] == "completed"
    with session_factory() as session:
        event = session.query(AuditEvent).filter_by(event_type="workflow_transition").one()
        assert event.configuration_version == "prototype-demo-v3"


def test_same_configuration_version_cannot_be_reused_for_changed_content(client) -> None:
    test_client, config_path, _ = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    definition = json.loads(config_path.read_text(encoding="utf-8"))
    definition["transitions"].append({"from_stage": "draft", "to_stage": "completed"})
    config_path.write_text(json.dumps(definition), encoding="utf-8")

    response = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/transitions",
        json={"target_stage": "completed", "actor_id": "tester"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["message"].startswith("Workflow configuration version is immutable")


def test_institution_scoped_record_and_audit_queries_hide_other_institution(client) -> None:
    test_client, _, _ = client
    institution_a = create_institution(test_client)
    institution_b = create_institution(test_client)
    record = create_record(test_client, institution_a["id"])

    read_response = test_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record['id']}"
    )
    history_response = test_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record['id']}/audit-events"
    )

    assert read_response.status_code == 404
    assert history_response.status_code == 404


def test_client_cannot_set_backend_controlled_record_fields(client) -> None:
    test_client, _, _ = client
    institution = create_institution(test_client)

    response = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records",
        json={"actor_id": "tester", "workflow_stage": "completed", "id": "caller-chosen"},
    )

    assert response.status_code == 422
