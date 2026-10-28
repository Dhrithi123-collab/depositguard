import hashlib
import json
import re
import struct
import zlib

import pytest

from app.models import AuditEvent, EvidenceCheck, FDRDocument, FDRDocumentVersion
from app.services.storage import StorageUnavailable

SYNTHETIC_PDF = b"%PDF-1.4\n% synthetic test fixture\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
CATEGORY = "illustrative_supporting_evidence"


def create_institution(test_client, name: str = "Synthetic Document Institute"):
    response = test_client.post("/api/institutions", json={"name": name, "actor_id": "synthetic-test-actor"})
    assert response.status_code == 201
    return response.json()


def create_record(test_client, institution_id: str):
    response = test_client.post(
        f"/api/institutions/{institution_id}/fdr-records",
        json={"instrument_reference": "SYNTHETIC-DOCUMENT-REF", "actor_id": "synthetic-test-actor"},
    )
    assert response.status_code == 201
    return response.json()


def upload_document(
    test_client,
    institution_id: str,
    record_id: str,
    *,
    content: bytes = SYNTHETIC_PDF,
    filename: str = "synthetic-evidence.pdf",
    media_type: str = "application/pdf",
    document_id: str | None = None,
):
    data = {"category_key": CATEGORY, "actor_id": "synthetic-uploader"}
    if document_id is not None:
        data["document_id"] = document_id
    return test_client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/documents",
        data=data,
        files={"file": (filename, content, media_type)},
    )


def check_integrity(test_client, institution_id: str, record_id: str, document_id: str, version_id: str):
    return test_client.post(
        f"/api/institutions/{institution_id}/fdr-records/{record_id}/documents/{document_id}/versions/{version_id}/integrity-checks",
        json={"actor_id": "synthetic-reviewer"},
    )


def png_chunk(kind: bytes, data: bytes) -> bytes:
    content = kind + data
    return struct.pack(">I", len(data)) + content + struct.pack(">I", zlib.crc32(content) & 0xFFFFFFFF)


SYNTHETIC_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    + png_chunk(b"IDAT", zlib.compress(b"\x00\x10\x20\x30"))
    + png_chunk(b"IEND", b"")
)


def test_allowed_pdf_upload_is_private_generated_and_hashed(upload_client) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = upload_document(test_client, institution["id"], record["id"], filename=r"..\..\secret.pdf")

    assert response.status_code == 201
    document = response.json()
    version = document["latest_version"]
    assert version["original_filename"] == "secret.pdf"
    assert version["sha256_digest"] == hashlib.sha256(SYNTHETIC_PDF).hexdigest()
    with session_factory() as session:
        row = session.query(FDRDocumentVersion).filter_by(id=version["id"]).one()
        assert re.fullmatch(r"[0-9a-f]{32}", row.storage_id)
        stored_path = storage._safe_path(row.storage_id)
        assert stored_path.is_relative_to(storage.root)
        assert stored_path.read_bytes() == SYNTHETIC_PDF
        assert row.original_filename == "secret.pdf"
    assert "storage_id" not in version
    assert str(storage.root) not in response.text


def test_allowed_png_is_validated_from_content_signature(upload_client) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = upload_document(
        test_client,
        institution["id"],
        record["id"],
        content=SYNTHETIC_PNG,
        filename="synthetic.png",
        media_type="application/octet-stream",
    )

    assert response.status_code == 201
    assert response.json()["latest_version"]["media_type"] == "image/png"
    version = response.json()["latest_version"]
    assert version["sha256_digest"] == hashlib.sha256(SYNTHETIC_PNG).hexdigest()
    with session_factory() as session:
        saved_version = session.get(FDRDocumentVersion, version["id"])
        assert storage._safe_path(saved_version.storage_id).read_bytes() == SYNTHETIC_PNG


def test_disallowed_extension_and_malformed_content_are_rejected(upload_client) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    disallowed = upload_document(
        test_client,
        institution["id"],
        record["id"],
        content=b"plain synthetic text",
        filename="not-allowed.txt",
        media_type="text/plain",
    )
    malformed = upload_document(
        test_client,
        institution["id"],
        record["id"],
        content=b"not a real pdf",
    )

    assert disallowed.status_code == 415
    assert malformed.status_code == 415
    with session_factory() as session:
        assert session.query(FDRDocument).count() == 0
        assert session.query(FDRDocumentVersion).count() == 0
    assert not storage.root.exists()


def test_missing_upload_file_is_rejected_without_creating_document_or_storage(upload_client) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    response = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents",
        data={"category_key": CATEGORY, "actor_id": "synthetic-uploader"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    with session_factory() as session:
        assert session.query(FDRDocument).count() == 0
        assert session.query(FDRDocumentVersion).count() == 0
    assert not storage.root.exists()


def test_private_storage_failure_is_reported_without_claiming_upload_success(upload_client, monkeypatch) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])

    async def fail_store(_upload, _policy):
        raise StorageUnavailable("synthetic storage outage")

    monkeypatch.setattr(storage, "store_upload", fail_store)
    response = upload_document(test_client, institution["id"], record["id"])

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "private_storage_unavailable"
    with session_factory() as session:
        assert session.query(FDRDocument).count() == 0
        assert session.query(FDRDocumentVersion).count() == 0
    assert not storage.root.exists()


def test_oversized_file_is_rejected_by_active_policy(upload_client) -> None:
    test_client, session_factory, storage, policy_path = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["max_file_size_bytes"] = 16
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    response = upload_document(test_client, institution["id"], record["id"])

    assert response.status_code == 413
    with session_factory() as session:
        assert session.query(FDRDocumentVersion).count() == 0
    assert not storage.root.exists()


def test_sha256_integrity_pass_and_audit_are_linked_to_exact_version(upload_client) -> None:
    test_client, session_factory, _, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    upload = upload_document(test_client, institution["id"], record["id"])
    document = upload.json()
    version = document["latest_version"]

    response = check_integrity(test_client, institution["id"], record["id"], document["id"], version["id"])

    assert response.status_code == 201
    check = response.json()
    assert check["document_version_id"] == version["id"]
    assert check["check_type"] == "sha256_integrity"
    assert check["result_status"] == "PASS"
    assert check["result_details"]["recorded_sha256"] == version["sha256_digest"]
    assert check["result_details"]["observed_sha256"] == version["sha256_digest"]
    with session_factory() as session:
        saved_check = session.query(EvidenceCheck).filter_by(id=check["id"]).one()
        event = session.query(AuditEvent).filter_by(event_type="document_integrity_checked").one()
        assert event.details["evidence_check_id"] == check["id"]
        assert event.details["document_version_id"] == version["id"]
        assert saved_check.document_version_id == version["id"]


def test_changed_stored_bytes_fail_integrity_without_changing_recorded_digest(upload_client) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    upload = upload_document(test_client, institution["id"], record["id"])
    document = upload.json()
    version = document["latest_version"]
    with session_factory() as session:
        stored_version = session.get(FDRDocumentVersion, version["id"])
        stored_path = storage._safe_path(stored_version.storage_id)
        original_digest = stored_version.sha256_digest
    stored_path.write_bytes(SYNTHETIC_PDF + b"changed")

    response = check_integrity(test_client, institution["id"], record["id"], document["id"], version["id"])

    assert response.status_code == 201
    assert response.json()["result_status"] == "FAIL"
    assert response.json()["result_details"]["recorded_sha256"] == original_digest
    assert response.json()["result_details"]["observed_sha256"] != original_digest
    with session_factory() as session:
        assert session.get(FDRDocumentVersion, version["id"]).sha256_digest == original_digest


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
def test_missing_or_unreadable_file_is_indeterminate_and_recorded(upload_client, monkeypatch, failure: str) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    upload = upload_document(test_client, institution["id"], record["id"])
    document = upload.json()
    version = document["latest_version"]
    with session_factory() as session:
        stored_version = session.get(FDRDocumentVersion, version["id"])
        storage_id = stored_version.storage_id
    if failure == "missing":
        storage._safe_path(storage_id).unlink()
    else:
        def cannot_read(_storage_id: str) -> str:
            raise PermissionError("synthetic unreadable-file condition")

        monkeypatch.setattr(storage, "sha256_digest", cannot_read)

    response = check_integrity(test_client, institution["id"], record["id"], document["id"], version["id"])

    assert response.status_code == 201
    assert response.json()["result_status"] == "INDETERMINATE"
    assert response.json()["result_details"]["observed_sha256"] is None
    assert "not completed" in response.json()["explanation"]


def test_new_upload_version_preserves_previous_metadata_and_bytes(upload_client) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    first_response = upload_document(test_client, institution["id"], record["id"], filename="first.pdf")
    first_document = first_response.json()
    first = first_document["latest_version"]
    with session_factory() as session:
        first_storage_id = session.get(FDRDocumentVersion, first["id"]).storage_id
    second_bytes = b"%PDF-1.7\n% second synthetic version\n%%EOF\n"

    second_response = upload_document(
        test_client,
        institution["id"],
        record["id"],
        content=second_bytes,
        filename="second.pdf",
        document_id=first_document["id"],
    )

    assert second_response.status_code == 201
    assert second_response.json()["id"] == first_document["id"]
    assert second_response.json()["latest_version"]["version_number"] == 2
    versions_response = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents/{first_document['id']}/versions"
    )
    versions = versions_response.json()
    assert [item["version_number"] for item in versions] == [1, 2]
    assert versions[0]["original_filename"] == "first.pdf"
    assert versions[0]["sha256_digest"] == hashlib.sha256(SYNTHETIC_PDF).hexdigest()
    assert versions[1]["sha256_digest"] == hashlib.sha256(second_bytes).hexdigest()
    assert storage._safe_path(first_storage_id).read_bytes() == SYNTHETIC_PDF
    with session_factory() as session:
        assert session.query(FDRDocumentVersion).filter_by(document_id=first_document["id"]).count() == 2


def test_integrity_checks_and_evidence_history_remain_linked_to_each_version(upload_client) -> None:
    test_client, session_factory, storage, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    first_upload = upload_document(test_client, institution["id"], record["id"], filename="first.pdf")
    document = first_upload.json()
    first_version = document["latest_version"]
    second_bytes = b"%PDF-1.7\n% second synthetic version\n%%EOF\n"
    second_upload = upload_document(
        test_client,
        institution["id"],
        record["id"],
        filename="second.pdf",
        content=second_bytes,
        document_id=document["id"],
    )
    second_version = second_upload.json()["latest_version"]

    first_check = check_integrity(test_client, institution["id"], record["id"], document["id"], first_version["id"])
    second_check = check_integrity(test_client, institution["id"], record["id"], document["id"], second_version["id"])
    history = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/evidence-checks"
    )

    assert first_check.status_code == second_check.status_code == 201
    assert first_check.json()["result_status"] == second_check.json()["result_status"] == "PASS"
    assert first_check.json()["document_version_id"] == first_version["id"]
    assert second_check.json()["document_version_id"] == second_version["id"]
    assert history.status_code == 200
    assert {item["id"]: item["document_version_id"] for item in history.json()} == {
        first_check.json()["id"]: first_version["id"],
        second_check.json()["id"]: second_version["id"],
    }
    with session_factory() as session:
        first_stored = session.get(FDRDocumentVersion, first_version["id"])
        second_stored = session.get(FDRDocumentVersion, second_version["id"])
        assert storage._safe_path(first_stored.storage_id).read_bytes() == SYNTHETIC_PDF
        assert storage._safe_path(second_stored.storage_id).read_bytes() == second_bytes


def test_missing_integrity_version_returns_404_without_recording_evidence(upload_client) -> None:
    test_client, session_factory, _, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    upload = upload_document(test_client, institution["id"], record["id"])
    document = upload.json()

    response = check_integrity(test_client, institution["id"], record["id"], document["id"], "missing-version")

    assert response.status_code == 404
    with session_factory() as session:
        assert session.query(EvidenceCheck).count() == 0


def test_list_documents_and_versions_are_scoped_to_institution_and_record(upload_client) -> None:
    test_client, _, _, _ = upload_client
    institution_a = create_institution(test_client, "Synthetic Institute A")
    institution_b = create_institution(test_client, "Synthetic Institute B")
    record_a = create_record(test_client, institution_a["id"])
    record_b = create_record(test_client, institution_b["id"])
    upload = upload_document(test_client, institution_a["id"], record_a["id"])
    document = upload.json()
    version_id = document["latest_version"]["id"]

    assert test_client.get(
        f"/api/institutions/{institution_a['id']}/fdr-records/{record_a['id']}/documents"
    ).status_code == 200
    other_list = test_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_a['id']}/documents"
    )
    other_versions = test_client.get(
        f"/api/institutions/{institution_b['id']}/fdr-records/{record_b['id']}/documents/{document['id']}/versions"
    )
    other_check = check_integrity(test_client, institution_b["id"], record_b["id"], document["id"], version_id)

    assert other_list.status_code == 404
    assert other_versions.status_code == 404
    assert other_check.status_code == 404


def test_invalid_document_category_and_upload_configuration_fail_closed(upload_client) -> None:
    test_client, session_factory, storage, policy_path = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    invalid_category = test_client.post(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/documents",
        data={"category_key": "unconfigured_category", "actor_id": "synthetic-uploader"},
        files={"file": ("synthetic.pdf", SYNTHETIC_PDF, "application/pdf")},
    )
    assert invalid_category.status_code == 422
    policy_path.write_text('{"version":"broken","max_file_size_bytes":-1,"allowed_file_types":[]}', encoding="utf-8")

    invalid_policy = upload_document(test_client, institution["id"], record["id"])

    assert invalid_policy.status_code == 503
    assert invalid_policy.json()["error"]["code"] == "upload_configuration_unavailable"
    with session_factory() as session:
        assert session.query(FDRDocument).count() == 0
        assert session.query(FDRDocumentVersion).count() == 0
    assert not storage.root.exists()


def test_upload_policy_version_cannot_be_reused_for_changed_content(upload_client) -> None:
    test_client, session_factory, storage, policy_path = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    first = upload_document(test_client, institution["id"], record["id"])
    first_document = first.json()
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["max_file_size_bytes"] -= 1
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    response = upload_document(test_client, institution["id"], record["id"], filename="another.pdf")

    assert response.status_code == 503
    assert "versions are immutable" in response.json()["error"]["message"]
    with session_factory() as session:
        saved_versions = session.query(FDRDocumentVersion).filter_by(document_id=first_document["id"]).all()
        assert len(saved_versions) == 1
        storage_id = saved_versions[0].storage_id
    assert storage._safe_path(storage_id).read_bytes() == SYNTHETIC_PDF


def test_upload_and_integrity_check_audit_events_are_recorded(upload_client) -> None:
    test_client, session_factory, _, _ = upload_client
    institution = create_institution(test_client)
    record = create_record(test_client, institution["id"])
    upload = upload_document(test_client, institution["id"], record["id"])
    document = upload.json()
    version = document["latest_version"]
    check = check_integrity(test_client, institution["id"], record["id"], document["id"], version["id"])

    assert check.status_code == 201
    with session_factory() as session:
        events = session.query(AuditEvent).filter_by(fdr_record_id=record["id"]).all()
        assert {event.event_type for event in events} >= {"document_uploaded", "document_integrity_checked"}
        uploaded = next(event for event in events if event.event_type == "document_uploaded")
        assert uploaded.details["document_version_id"] == version["id"]

    history = test_client.get(
        f"/api/institutions/{institution['id']}/fdr-records/{record['id']}/evidence-checks"
    )
    assert history.status_code == 200
    assert history.json()[0]["document_version_id"] == version["id"]
