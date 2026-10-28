import json

from app.models import AuditEvent, EvidenceCheck, FDRDocument, FDRDocumentVersion, FDRRelationship


def create_institution(client):
    response = client.post("/api/institutions", json={"name": "Synthetic Graph Institute", "actor_id": "graph-tester"})
    assert response.status_code == 201
    return response.json()


def create_record(client, institution_id):
    response = client.post(
        f"/api/institutions/{institution_id}/fdr-records",
        json={"instrument_reference": None, "actor_id": "graph-tester"},
    )
    assert response.status_code == 201
    return response.json()


def create_link(client, institution_id, source_id, target_id, kind="related_to"):
    return client.post(
        f"/api/institutions/{institution_id}/fdr-records/{source_id}/relationships",
        json={
            "target_record_id": target_id,
            "relationship_type": kind,
            "review_status": "unreviewed",
            "note": "Synthetic test association",
            "actor_id": "graph-tester",
        },
    )


def fdr_order(response):
    return [node["entity_id"] for node in response.json()["nodes"] if node["entity_type"] == "fdr_record"]


def test_relationship_create_list_and_audit(client):
    test_client, _, session_factory = client
    institution = create_institution(test_client)
    source = create_record(test_client, institution["id"])
    target = create_record(test_client, institution["id"])

    response = create_link(test_client, institution["id"], source["id"], target["id"], "renewal_of")

    assert response.status_code == 201
    assert response.json()["relationship_label"] == "Renewal of"
    assert response.json()["review_status"] == "unreviewed"
    listed = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{source['id']}/relationships")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == response.json()["id"]
    with session_factory() as session:
        relation = session.get(FDRRelationship, response.json()["id"])
        event = session.query(AuditEvent).filter_by(event_type="fdr_relationship_recorded").one()
        assert relation.source_record_id == source["id"]
        assert event.details["target_record_id"] == target["id"]


def test_rejects_invalid_self_unknown_duplicate_and_cross_institution_relationships(client):
    test_client, _, _ = client
    institution_a = create_institution(test_client)
    institution_b = create_institution(test_client)
    a = create_record(test_client, institution_a["id"])
    b = create_record(test_client, institution_a["id"])
    foreign = create_record(test_client, institution_b["id"])

    assert create_link(test_client, institution_a["id"], a["id"], a["id"]).status_code == 422
    assert create_link(test_client, institution_a["id"], a["id"], foreign["id"]).status_code == 404
    assert create_link(test_client, institution_a["id"], a["id"], b["id"], "not_configured").status_code == 422
    assert create_link(test_client, institution_a["id"], a["id"], b["id"]).status_code == 201
    assert create_link(test_client, institution_a["id"], a["id"], b["id"]).status_code == 409


def test_cycle_rules_prohibit_renewal_cycles_but_allow_related_cycles(client):
    test_client, _, _ = client
    institution = create_institution(test_client)
    a, b, c = [create_record(test_client, institution["id"]) for _ in range(3)]

    assert create_link(test_client, institution["id"], a["id"], b["id"], "renewal_of").status_code == 201
    assert create_link(test_client, institution["id"], b["id"], c["id"], "renewal_of").status_code == 201
    rejected = create_link(test_client, institution["id"], c["id"], a["id"], "renewal_of")
    assert rejected.status_code == 422
    assert "cycle" in rejected.json()["error"]["message"]

    assert create_link(test_client, institution["id"], a["id"], b["id"], "related_to").status_code == 201
    assert create_link(test_client, institution["id"], b["id"], c["id"], "related_to").status_code == 201
    assert create_link(test_client, institution["id"], c["id"], a["id"], "related_to").status_code == 201


def test_bfs_dfs_visit_orders_loops_and_depth_limit(client):
    test_client, _, _ = client
    institution = create_institution(test_client)
    a, b, c, d, e = [create_record(test_client, institution["id"]) for _ in range(5)]
    for source, target in [(a, b), (a, c), (b, d), (c, e)]:
        assert create_link(test_client, institution["id"], source["id"], target["id"]).status_code == 201

    bfs = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{a['id']}/graph/bfs")
    dfs = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{a['id']}/graph/dfs")
    depth_one = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{a['id']}/graph/bfs?max_depth=1"
    )
    too_deep = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{a['id']}/graph?max_depth=7"
    )

    assert bfs.status_code == dfs.status_code == depth_one.status_code == 200
    first, second = sorted([b, c], key=lambda item: item["id"])
    children = {b["id"]: d["id"], c["id"]: e["id"]}
    assert fdr_order(bfs) == [a["id"], first["id"], second["id"], children[first["id"]], children[second["id"]]]
    assert fdr_order(dfs) == [a["id"], first["id"], children[first["id"]], second["id"], children[second["id"]]]
    assert all(node["depth"] <= 1 for node in depth_one.json()["nodes"])
    assert {node["entity_id"] for node in depth_one.json()["nodes"] if node["entity_type"] == "fdr_record"} == {
        a["id"], b["id"], c["id"]
    }
    assert too_deep.status_code == 422
    assert len({(n["entity_type"], n["entity_id"]) for n in bfs.json()["nodes"]}) == len(bfs.json()["nodes"])
    assert all(edge["traversal_depth"] == bfs.json()["nodes"][i + 1]["depth"] for i, edge in enumerate(bfs.json()["edges"]))


def test_no_connected_fdr_records_and_missing_record_are_handled(client):
    test_client, _, _ = client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/graph")
    missing = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/missing/graph")

    assert response.status_code == 200
    assert fdr_order(response) == [record["id"]]
    assert len(response.json()["nodes"]) == 2  # start plus the record-created audit event
    assert missing.status_code == 404


def test_graph_includes_document_version_and_exact_integrity_evidence(upload_client):
    test_client, session_factory, _, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    upload = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents",
        data={"category_key": "illustrative_supporting_evidence", "actor_id": "graph-uploader"},
        files={"file": ("synthetic.pdf", b"%PDF-1.4\nsynthetic\n%%EOF\n", "application/pdf")},
    )
    assert upload.status_code == 201
    document = upload.json()
    version = document["latest_version"]
    checked = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents/{document['id']}/versions/{version['id']}/integrity-checks",
        json={"actor_id": "graph-reviewer"},
    )
    assert checked.status_code == 201

    graph = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/graph")
    assert graph.status_code == 200
    node_ids = {(node["entity_type"], node["entity_id"]) for node in graph.json()["nodes"]}
    assert ("document", document["id"]) in node_ids
    assert ("document_version", version["id"]) in node_ids
    assert ("evidence_check", checked.json()["id"]) in node_ids
    with session_factory() as session:
        assert session.get(FDRDocument, document["id"]).fdr_record_id == record["id"]
        assert session.get(FDRDocumentVersion, version["id"]).document_id == document["id"]
        assert session.get(EvidenceCheck, checked.json()["id"]).document_version_id == version["id"]


def test_invalid_graph_configuration_fails_closed(client):
    test_client, _, _ = client
    # The graph-policy override is created in the fixture's temp root; the API returns a distinct safe error.
    from app.api.routes import get_graph_service
    service = test_client.app.dependency_overrides[get_graph_service]()
    policy = json.loads(service.policy_path.read_text(encoding="utf-8"))
    policy["max_traversal_depth"] = 100
    service.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/graph")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "graph_policy_unavailable"


def test_node_limit_returns_explicit_truncated_result(client):
    test_client, _, _ = client
    from app.api.routes import get_graph_service
    service = test_client.app.dependency_overrides[get_graph_service]()
    policy = json.loads(service.policy_path.read_text(encoding="utf-8"))
    policy["max_nodes"] = 2
    service.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    institution = create_institution(test_client)
    a, b, c = [create_record(test_client, institution["id"]) for _ in range(3)]
    assert create_link(test_client, institution["id"], a["id"], b["id"]).status_code == 201
    assert create_link(test_client, institution["id"], a["id"], c["id"]).status_code == 201

    response = test_client.get(f"/api/institutions/{institution['id']}/fdr-records/{a['id']}/graph")

    assert response.status_code == 200
    assert len(response.json()["nodes"]) == 2
    assert response.json()["max_nodes"] == 2
    assert response.json()["truncated"] is True
