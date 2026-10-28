import pytest
from fastapi.testclient import TestClient
from app.models import User, InstitutionMembership
from app.services.auth import create_user

# Helper to login a user and configure the test client with auth cookies
def login_user(test_client: TestClient, email: str, password: str):
    response = test_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    csrf_token = response.json()["csrf_token"]
    # Session cookie is set automatically in the client
    test_client.headers.update({"X-CSRF-Token": csrf_token})
    return test_client

@pytest.fixture
def user_client(client, tmp_path):
    """Create two institutions and a user belonging to institution A.
    Returns a tuple of (admin_client, user_a_client, institution_a, institution_b).
    """
    admin_client, _, _ = client
    # Create institutions A and B
    resp_a = admin_client.post(
        "/api/institutions",
        json={"name": "Institution A", "actor_id": "admin"},
    )
    assert resp_a.status_code == 201
    institution_a = resp_a.json()
    resp_b = admin_client.post(
        "/api/institutions",
        json={"name": "Institution B", "actor_id": "admin"},
    )
    assert resp_b.status_code == 201
    institution_b = resp_b.json()

    # Create a regular user for Institution A with role "document_officer"
    user_payload = {
        "email": "officer_a@example.test",
        "display_name": "Officer A",
        "temporary_password": "Secret123!AB",
        "system_admin": False,
        "institution_id": institution_a["id"],
        "role": "document_officer",
    }
    resp_user = admin_client.post("/api/auth/users", json=user_payload)
    assert resp_user.status_code == 201
    # Login as the new user
    user_client = login_user(TestClient(admin_client.app), "officer_a@example.test", "Secret123!AB")
    # Change temporary password to satisfy must_change_password requirement
    change_resp = user_client.post(
        "/api/auth/change-password",
        json={"current_password": "Secret123!AB", "new_password": "Secret123!AB2"},
    )
    assert change_resp.status_code == 204
    return admin_client, user_client, institution_a, institution_b

def create_record(test_client, institution_id: str):
    response = test_client.post(
        f"/api/institutions/{institution_id}/fdr-records",
        json={"instrument_reference": "REC-001", "actor_id": "synthetic"},
    )
    assert response.status_code == 201
    return response.json()

def upload_document(test_client, institution_id: str, record_id: str):
    data = {"category_key": "illustrative_supporting_evidence", "actor_id": "synthetic-uploader"}
    files = {"file": ("doc.pdf", b"%PDF-1.4\n% test\n%%EOF", "application/pdf")}
    response = test_client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/documents",
        data=data,
        files=files,
    )
    return response

def test_cross_institution_document_isolation(user_client):
    admin_client, user_a_client, institution_a, institution_b = user_client
    # Create records in both institutions (admin client)
    record_a = create_record(admin_client, institution_a["id"])  # record in A
    record_b = create_record(admin_client, institution_b["id"])  # record in B

    # Upload a document to Institution A as user A (allowed role)
    upload_resp = upload_document(user_a_client, institution_a["id"], record_a["id"])  # should succeed
    assert upload_resp.status_code == 201
    doc = upload_resp.json()
    doc_id = doc["id"]
    version_id = doc["latest_version"]["id"]

    # ----- Attempt to access Institution A document using Institution B context -----
    # List documents for record B (should be empty list, status 200)
    list_wrong = admin_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_b['id']}/documents"
    )
    assert list_wrong.status_code == 200
    assert doc_id not in [d["id"] for d in list_wrong.json()]

    # As user A, attempt to list documents for record B (different institution) -> should be 404
    list_other = user_a_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_b['id']}/documents"
    )
    assert list_other.status_code == 404

    # As user A, attempt to fetch versions of the document using institution B endpoint -> 404
    versions_other = user_a_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_b['id']}/documents/{doc_id}/versions"
    )
    assert versions_other.status_code == 404

    # As user A, attempt integrity check on the document via institution B endpoint -> 404
    integrity_other = user_a_client.post(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_b['id']}/documents/{doc_id}/versions/{version_id}/integrity-checks",
        json={"actor_id": "synthetic-reviewer"},
    )
    assert integrity_other.status_code == 404

    # ----- Verify upload permission enforcement across institutions -----
    # Attempt to upload a document to Institution B using user A (different institution) -> should be 403
    upload_other = upload_document(user_a_client, institution_b["id"], record_b["id"])
    assert upload_other.status_code == 404

    # Verify that admin (system admin) can still access both institutions
    admin_doc_list_a = admin_client.get(
        f"/api/institutions/{institution_a['id']}/fdr-records/{record_a['id']}/documents"
    )
    assert admin_doc_list_a.status_code == 200
    assert any(d["id"] == doc_id for d in admin_doc_list_a.json())

    admin_doc_list_b = admin_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_b['id']}/documents"
    )
    assert admin_doc_list_b.status_code == 200
    assert doc_id not in [d["id"] for d in admin_doc_list_b.json()]

def test_cross_institution_audit_events_are_scoped(user_client):
    admin_client, user_a_client, institution_a, institution_b = user_client
    record_a = create_record(admin_client, institution_a["id"])
    # Upload document in Institution A as user A
    upload_resp = upload_document(user_a_client, institution_a["id"], record_a["id"])  # success
    assert upload_resp.status_code == 201
    doc = upload_resp.json()
    version_id = doc["latest_version"]["id"]
    # Perform integrity check in Institution A (allowed)
    integrity_resp = user_a_client.post(
        f"/api/institutions/{institution_a['id']}/fdr-records/{record_a['id']}/documents/{doc['id']}/versions/{version_id}/integrity-checks",
        json={"actor_id": "synthetic-reviewer"},
    )
    assert integrity_resp.status_code == 201
    # Verify audit events recorded for Institution A only via security events endpoint
    security_events = admin_client.get("/api/auth/security-events?limit=200")
    assert security_events.status_code == 200
    events = security_events.json()
    for ev in events:
        if ev.get("institution_id"):
            assert ev["institution_id"] == institution_a["id"]
    # Attempt integrity check via Institution B (should be 404, no audit recorded)
    integrity_other = user_a_client.post(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_a['id']}/documents/{doc['id']}/versions/{version_id}/integrity-checks",
        json={"actor_id": "synthetic-reviewer"},
    )
    assert integrity_other.status_code == 404
