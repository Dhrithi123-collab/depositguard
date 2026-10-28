import json
from datetime import datetime, timedelta, timezone

from app.api.routes import get_priority_service
from app.models import EvidenceCheck, FDRRecord, ReviewPriorityCalculation


def create_institution(client, label="Priority Test Institute"):
    response = client.post("/api/institutions", json={"name": label, "actor_id": "priority-tester"})
    assert response.status_code == 201
    return response.json()


def create_record(client, institution_id):
    response = client.post(
        f"/api/institutions/{institution_id}/fdr-records",
        json={"instrument_reference": None, "actor_id": "priority-tester"},
    )
    assert response.status_code == 201
    return response.json()


def submit_record(client, institution_id, record_id):
    response = client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/transitions",
        json={"target_stage": "submitted", "actor_id": "priority-tester"},
    )
    assert response.status_code == 200


def priority_service(test_client):
    return test_client.app.dependency_overrides[get_priority_service]()


def test_score_is_explainable_persisted_and_marks_unavailable_inputs(client):
    test_client, workflow_path, session_factory = client
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["version"] = "priority-workflow-required-v2"
    workflow["document_requirements"][0]["required"] = True
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    submit_record(test_client, institution["id"], record["id"])

    response = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/urgency-score"
    )

    assert response.status_code == 200
    body = response.json()
    by_factor = {factor["factor"]: factor for factor in body["factors"]}
    assert by_factor["missing_required_documents"]["points"] == 12
    assert "illustrative_supporting_evidence" in by_factor["missing_required_documents"]["explanation"]
    assert by_factor["evidence_attention"]["points"] == 5
    assert by_factor["evidence_attention"]["evaluated"] is False
    assert any("No deadline field" in item for item in body["missing_inputs"])
    assert any("No SHA-256 integrity checks" in item for item in body["missing_inputs"])
    assert body["policy_version"] == "prototype-priority-v1"
    assert len(body["policy_digest"]) == 64
    with session_factory() as session:
        saved = session.get(ReviewPriorityCalculation, body["calculation_id"])
        assert saved.score == body["score"]
        assert saved.policy_digest == body["policy_digest"]
        assert saved.factors[0]["points"] == 12


def test_policy_api_validates_and_configuration_version_changes_scoring(client):
    test_client, _, _ = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    submit_record(test_client, institution["id"], record["id"])
    service = priority_service(test_client)
    policy = json.loads(service.policy_path.read_text(encoding="utf-8"))
    first = test_client.get("/api/review-priority/policy")
    initial = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/urgency-score"
    )
    assert first.status_code == initial.status_code == 200

    policy["version"] = "prototype-priority-v2"
    policy["factors"]["evidence_attention"]["points_if_no_checks"] = 20
    service.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    changed = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/urgency-score"
    )

    assert changed.status_code == 200
    assert changed.json()["score"] == initial.json()["score"] + 15
    assert changed.json()["policy_version"] == "prototype-priority-v2"
    assert changed.json()["policy_digest"] != initial.json()["policy_digest"]

    policy["factors"]["evidence_attention"]["points_if_no_checks"] = 21
    service.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    immutable = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/urgency-score"
    )
    assert immutable.status_code == 503
    assert "immutable" in immutable.json()["error"]["message"]


def test_invalid_priority_configuration_fails_closed(client):
    test_client, _, _ = client
    service = priority_service(test_client)
    base = json.loads(service.policy_path.read_text(encoding="utf-8"))
    invalid_variants = []
    policy = json.loads(json.dumps(base))
    policy["factors"]["unexpected_factor"] = {"enabled": True}
    invalid_variants.append(policy)
    policy = json.loads(json.dumps(base))
    policy["categories"][1]["minimum_score"] = 0
    invalid_variants.append(policy)
    policy = json.loads(json.dumps(base))
    policy["version"] = ""
    invalid_variants.append(policy)
    policy = json.loads(json.dumps(base))
    policy["factors"]["review_wait"]["max_points"] = 101
    invalid_variants.append(policy)
    policy = json.loads(json.dumps(base))
    policy["eligible_stages"] = ["unknown_stage"]
    invalid_variants.append(policy)

    for policy in invalid_variants:
        service.policy_path.write_text(json.dumps(policy), encoding="utf-8")
        response = test_client.get("/api/review-priority/policy")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "priority_configuration_unavailable"


def test_priority_queue_orders_scores_ties_deduplicates_refreshes_and_excludes_ineligible(client):
    test_client, _, session_factory = client
    institution = create_institution(test_client)
    records = [create_record(test_client, institution["id"]) for _ in range(4)]
    for item in records:
        submit_record(test_client, institution["id"], item["id"])
    policy_service = priority_service(test_client)
    policy = json.loads(policy_service.policy_path.read_text(encoding="utf-8"))
    policy["factors"]["review_wait"]["minimum_wait_days"] = 0
    policy["factors"]["review_wait"]["points_per_day_after_threshold"] = 5
    policy_service.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    # Make two records a deterministic tie for score and both time fields.
    tied_time = datetime.now(timezone.utc)
    with session_factory() as session:
        first = session.get(FDRRecord, records[0]["id"])
        second = session.get(FDRRecord, records[1]["id"])
        first.updated_at = tied_time
        second.updated_at = tied_time
        first.created_at = tied_time
        second.created_at = tied_time
        older = session.get(FDRRecord, records[2]["id"])
        older.updated_at = tied_time - timedelta(days=10)
        session.commit()
    # Complete the fourth record; it must no longer appear in the eligible review queue.
    test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{records[3]['id']}/transitions",
        json={"target_stage": "review", "actor_id": "priority-tester"},
    )
    test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{records[3]['id']}/transitions",
        json={"target_stage": "completed", "actor_id": "priority-tester"},
    )

    endpoint = f"/api/institutions/{institution['id']}/review-priority-queue"
    first_response = test_client.get(endpoint)
    second_response = test_client.get(endpoint)

    assert first_response.status_code == second_response.status_code == 200
    expected = [records[2]["id"], *sorted([records[0]["id"], records[1]["id"]])]
    assert [item["record_id"] for item in first_response.json()["items"]] == expected
    assert [item["record_id"] for item in second_response.json()["items"]] == expected
    assert len({item["record_id"] for item in first_response.json()["items"]}) == 3
    assert all(item["relevant_deadline"] is None for item in first_response.json()["items"])
    with session_factory() as session:
        assert session.query(ReviewPriorityCalculation).count() == 6


def test_priority_queue_and_score_are_institution_scoped(client):
    test_client, _, _ = client
    institution_a = create_institution(test_client, "Synthetic Institution A")
    institution_b = create_institution(test_client, "Synthetic Institution B")
    record_a = create_record(test_client, institution_a["id"])
    record_b = create_record(test_client, institution_b["id"])
    submit_record(test_client, institution_a["id"], record_a["id"])
    submit_record(test_client, institution_b["id"], record_b["id"])

    queue = test_client.get(f"/api/institutions/{institution_a['id']}/review-priority-queue")
    foreign = test_client.get(
        f"/api/institutions/{institution_a['id']}/fdr-records/{record_b['id']}/urgency-score"
    )

    assert queue.status_code == 200
    assert [item["record_id"] for item in queue.json()["items"]] == [record_a["id"]]
    assert foreign.status_code == 404


def test_priority_queue_recalculates_after_required_document_upload(upload_client):
    test_client, _, _, _ = upload_client
    from app.api.routes import get_workflow_service
    workflow_service = test_client.app.dependency_overrides[get_workflow_service]()
    workflow = json.loads(workflow_service.config_path.read_text(encoding="utf-8"))
    workflow["version"] = "priority-required-docs-v2"
    workflow["document_requirements"][0]["required"] = True
    workflow_service.config_path.write_text(json.dumps(workflow), encoding="utf-8")
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    submit_record(test_client, institution["id"], record["id"])
    score_url = f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/urgency-score"
    before = test_client.get(score_url)
    assert before.status_code == 200
    before_factors = {factor["factor"]: factor["points"] for factor in before.json()["factors"]}
    assert before_factors["missing_required_documents"] == 12

    uploaded = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents",
        data={"category_key": "illustrative_supporting_evidence", "actor_id": "priority-uploader"},
        files={"file": ("synthetic.pdf", b"%PDF-1.4\nsynthetic\n%%EOF\n", "application/pdf")},
    )
    after = test_client.get(score_url)

    assert uploaded.status_code == 201
    assert after.status_code == 200
    after_factors = {factor["factor"]: factor["points"] for factor in after.json()["factors"]}
    assert after_factors["missing_required_documents"] == 0
    assert after.json()["score"] == before.json()["score"] - 12


def test_failed_and_indeterminate_checks_add_configured_explainable_points(upload_client):
    test_client, session_factory, _, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    submit_record(test_client, institution["id"], record["id"])
    uploaded = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents",
        data={"category_key": "illustrative_supporting_evidence", "actor_id": "priority-uploader"},
        files={"file": ("synthetic.pdf", b"%PDF-1.4\nsynthetic\n%%EOF\n", "application/pdf")},
    ).json()
    version = uploaded["latest_version"]
    checked = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents/{uploaded['id']}/versions/{version['id']}/integrity-checks",
        json={"actor_id": "priority-reviewer"},
    )
    assert checked.status_code == 201
    with session_factory() as session:
        check = session.get(EvidenceCheck, checked.json()["id"])
        check.result_status = "FAIL"
        session.commit()

    failed = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/urgency-score"
    )
    assert failed.status_code == 200
    failed_factor = next(item for item in failed.json()["factors"] if item["factor"] == "evidence_attention")
    assert failed_factor["points"] == 20
    assert "1 FAIL" in failed_factor["explanation"]

    with session_factory() as session:
        check = session.get(EvidenceCheck, checked.json()["id"])
        check.result_status = "INDETERMINATE"
        session.commit()
    indeterminate = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/urgency-score"
    )
    factor = next(item for item in indeterminate.json()["factors"] if item["factor"] == "evidence_attention")
    assert factor["points"] == 10
    assert "1 INDETERMINATE" in factor["explanation"]

