from sqlalchemy import select
from datetime import timedelta

from app.models import AuthSession, AuditEvent, Institution, InstitutionMembership, User
from app.services.auth import create_user, now_utc

TEST_PASSWORD = "synthetic-test-password"


def provision(client, session_factory, *, email: str, role: str, institution_id: str, active: bool = True) -> str:
    with session_factory() as db:
        user = create_user(db, email=email, display_name=email.split("@")[0], password=TEST_PASSWORD, must_change_password=False)
        user.is_active = active
        db.add(InstitutionMembership(user_id=user.id, institution_id=institution_id, role=role))
        db.commit()
        user_id = user.id
    return user_id


def login(client, email: str) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


def create_institution(client, name: str) -> str:
    response = client.post("/api/institutions", json={"name": name, "actor_id": "forged-actor-label"})
    assert response.status_code == 201
    return response.json()["id"]


def test_protected_routes_require_authentication(client) -> None:
    test_client, _, _ = client
    test_client.cookies.clear()
    test_client.headers.pop("X-CSRF-Token", None)
    response = test_client.get("/api/institutions")
    assert response.status_code == 401
    assert test_client.get("/api/health").status_code == 200


def test_login_password_hash_and_logout_revocation(client) -> None:
    test_client, _, session_factory = client
    test_client.cookies.clear()
    failed = test_client.post("/api/auth/login", json={"email": "admin@example.test", "password": "not-the-password"})
    assert failed.status_code == 401
    signed_in = login(test_client, "admin@example.test")
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email_normalized == "admin@example.test"))
        assert user is not None
        assert user.password_hash != "synthetic-test-password"
        assert user.password_hash.startswith("$argon2id$")
        assert db.scalar(select(AuthSession.token_hash).where(AuthSession.user_id == user.id))
    assert test_client.get("/api/auth/session").json()["user"]["id"] == signed_in["user"]["id"]
    assert test_client.post("/api/auth/logout", headers={"X-CSRF-Token": signed_in["csrf_token"]}).status_code == 204
    assert test_client.get("/api/institutions").status_code == 401


def test_csrf_required_for_mutations(client) -> None:
    test_client, _, _ = client
    test_client.headers.pop("X-CSRF-Token", None)
    response = test_client.post("/api/institutions", json={"name": "Should Not Exist", "actor_id": "forged"})
    assert response.status_code == 403


def test_membership_scopes_reads_and_caller_actor_id_is_ignored(client) -> None:
    test_client, _, session_factory = client
    admin_id = test_client.get("/api/auth/session").json()["user"]["id"]
    institution_a = create_institution(test_client, "Synthetic Institution A")
    institution_b = create_institution(test_client, "Synthetic Institution B")
    assert {item["id"] for item in test_client.get("/api/institutions").json()} == {institution_a, institution_b}
    record_a = test_client.post(f"/api/institutions/{institution_a}/fdr-records", json={"instrument_reference": "A-001", "actor_id": "forged"}).json()
    user_id = provision(test_client, session_factory, email="auditor-a@example.test", role="auditor", institution_id=institution_a)
    login(test_client, "auditor-a@example.test")

    assert test_client.get("/api/institutions").json()[0]["id"] == institution_a
    assert test_client.get(f"/api/institutions/{institution_a}/fdr-records/{record_a['id']}").status_code == 200
    assert test_client.get(f"/api/institutions/{institution_b}/fdr-records").status_code == 404
    assert test_client.post(f"/api/institutions/{institution_b}/fdr-records", json={"instrument_reference": "NO-CROSS-WRITE", "actor_id": "forged"}).status_code == 404
    assert test_client.post(
        f"/api/institutions/{institution_b}/fdr-records/{record_a['id']}/transitions",
        json={"target_stage": "submitted", "actor_id": "forged"},
    ).status_code == 404
    assert test_client.post(f"/api/institutions/{institution_a}/fdr-records", json={"instrument_reference": "NO-WRITE", "actor_id": "forged"}).status_code == 403
    with session_factory() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.fdr_record_id == record_a["id"], AuditEvent.event_type == "record_created"))
        assert event is not None and event.actor_id == admin_id and event.actor_id != "forged"


def test_document_officer_may_upload_only_within_membership_and_auditor_is_read_only(client) -> None:
    test_client, _, session_factory = client
    institution_a = create_institution(test_client, "Synthetic Documents A")
    institution_b = create_institution(test_client, "Synthetic Documents B")
    record_a = test_client.post(f"/api/institutions/{institution_a}/fdr-records", json={"instrument_reference": "DOC-A", "actor_id": "admin"}).json()
    record_b = test_client.post(f"/api/institutions/{institution_b}/fdr-records", json={"instrument_reference": "DOC-B", "actor_id": "admin"}).json()
    provision(test_client, session_factory, email="officer-a@example.test", role="document_officer", institution_id=institution_a)
    login(test_client, "officer-a@example.test")
    form = {"category_key": "illustrative_supporting_evidence", "actor_id": "forged-actor"}
    fixture = ("synthetic.pdf", b"%PDF-1.4\nsynthetic\n%%EOF", "application/pdf")
    allowed = test_client.post(f"/api/institutions/{institution_a}/fdr-records/{record_a['id']}/documents", data=form, files={"file": fixture})
    denied = test_client.post(f"/api/institutions/{institution_b}/fdr-records/{record_b['id']}/documents", data=form, files={"file": fixture})
    assert allowed.status_code == 201
    assert denied.status_code == 404
    with session_factory() as db:
        document = db.get(__import__("app.models", fromlist=["FDRDocument"]).FDRDocument, allowed.json()["id"])
        assert document is not None and document.created_by != "forged-actor"


def test_deactivated_user_sessions_are_revoked(client) -> None:
    test_client, _, session_factory = client
    institution_id = create_institution(test_client, "Synthetic Deactivation")
    user_id = provision(test_client, session_factory, email="disabled@example.test", role="auditor", institution_id=institution_id)
    login(test_client, "disabled@example.test")
    with session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.is_active = False
        db.commit()
    assert test_client.get("/api/institutions").status_code == 401


def test_non_admin_cannot_provision_accounts(client) -> None:
    test_client, _, session_factory = client
    institution_id = create_institution(test_client, "Synthetic Admin Scope")
    provision(test_client, session_factory, email="reviewer@example.test", role="reviewer", institution_id=institution_id)
    login(test_client, "reviewer@example.test")
    response = test_client.post("/api/auth/users", json={
        "email": "privilege@example.test", "display_name": "Injected Admin",
        "temporary_password": TEST_PASSWORD, "system_admin": True,
    })
    assert response.status_code == 403


def test_temporary_password_must_be_changed_before_workspace_api(client) -> None:
    test_client, _, session_factory = client
    with session_factory() as db:
        create_user(db, email="temporary@example.test", display_name="Temporary User", password=TEST_PASSWORD)
        db.commit()
    signed_in = login(test_client, "temporary@example.test")
    assert test_client.get("/api/institutions").status_code == 403
    changed = test_client.post("/api/auth/change-password", json={
        "current_password": TEST_PASSWORD, "new_password": "synthetic-new-password",
    })
    assert changed.status_code == 204
    assert test_client.get("/api/institutions").status_code == 200
    assert signed_in["user"]["must_change_password"] is True


def test_expired_session_is_rejected(client) -> None:
    test_client, _, session_factory = client
    signed_in = test_client.get("/api/auth/session").json()
    token = test_client.cookies.get("depositguard_session")
    assert token
    from app.services.auth import hash_secret
    with session_factory() as db:
        auth_session = db.get(AuthSession, hash_secret(token))
        assert auth_session is not None
        auth_session.expires_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert test_client.get("/api/institutions").status_code == 401
    assert test_client.get("/api/auth/session").status_code == 401
    assert signed_in["user"]["id"]


def test_ten_failed_logins_are_rate_limited(client) -> None:
    test_client, _, _ = client
    test_client.cookies.clear()
    for _ in range(10):
        response = test_client.post("/api/auth/login", json={
            "email": "locked@example.test", "password": "wrong-synthetic-password",
        })
        assert response.status_code == 401
    blocked = test_client.post("/api/auth/login", json={
        "email": "locked@example.test", "password": TEST_PASSWORD,
    })
    assert blocked.status_code == 429


def test_cross_institution_nested_document_evidence_and_relationship_ids_are_denied(client) -> None:
    test_client, _, session_factory = client
    institution_a = create_institution(test_client, "Synthetic Isolation A")
    institution_b = create_institution(test_client, "Synthetic Isolation B")
    record_a = test_client.post(f"/api/institutions/{institution_a}/fdr-records", json={"instrument_reference": "ISO-A", "actor_id": "admin"}).json()
    record_b = test_client.post(f"/api/institutions/{institution_b}/fdr-records", json={"instrument_reference": "ISO-B", "actor_id": "admin"}).json()
    upload = test_client.post(
        f"/api/institutions/{institution_b}/fdr-records/{record_b['id']}/documents",
        data={"category_key": "illustrative_supporting_evidence", "actor_id": "admin"},
        files={"file": ("synthetic.pdf", b"%PDF-1.4\nsynthetic\n%%EOF", "application/pdf")},
    )
    assert upload.status_code == 201
    version = upload.json()["latest_version"]
    provision(test_client, session_factory, email="reviewer-isolation@example.test", role="reviewer", institution_id=institution_a)
    login(test_client, "reviewer-isolation@example.test")

    assert test_client.get(f"/api/institutions/{institution_b}/fdr-records/{record_b['id']}").status_code == 404
    assert test_client.get(f"/api/institutions/{institution_b}/fdr-records/{record_b['id']}/audit-events").status_code == 404
    assert test_client.get(f"/api/institutions/{institution_b}/fdr-records/{record_b['id']}/evidence-checks").status_code == 404
    nested_integrity = test_client.post(
        f"/api/institutions/{institution_a}/fdr-records/{record_b['id']}/documents/{upload.json()['id']}/versions/{version['id']}/integrity-checks",
        json={"actor_id": "forged"},
    )
    assert nested_integrity.status_code == 404
    cross_relationship = test_client.post(
        f"/api/institutions/{institution_a}/fdr-records/{record_a['id']}/relationships",
        json={"target_record_id": record_b["id"], "relationship_type": "related_to", "actor_id": "forged"},
    )
    assert cross_relationship.status_code == 404


def test_user_registration_without_institution_and_password_policy(client) -> None:
    test_client, _, session_factory = client
    test_client.cookies.clear()
    test_client.headers.pop("X-CSRF-Token", None)

    # 1. Password shorter than 6 characters rejected
    short_resp = test_client.post("/api/auth/register", json={
        "email": "short@example.test",
        "display_name": "Short User",
        "password": "12345",
        "role": "auditor",
    })
    assert short_resp.status_code == 422

    # 2. Cannot register as system_admin
    admin_resp = test_client.post("/api/auth/register", json={
        "email": "hacker@example.test",
        "display_name": "Hacker",
        "password": "valid6",
        "role": "system_admin",
    })
    assert admin_resp.status_code == 422

    # 3. Successful registration with exactly 6 character password without institution
    reg_resp = test_client.post("/api/auth/register", json={
        "email": "demo-auditor@example.test",
        "display_name": "Demo Auditor",
        "password": "valid6",
        "role": "auditor",
    })
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert reg_data["user"]["email"] == "demo-auditor@example.test"
    assert reg_data["user"]["active"] is True
    assert reg_data["user"]["system_admin"] is False
    assert reg_data["user"]["memberships"] == []
    assert "csrf_token" in reg_data

    # Session cookie established immediately
    assert "depositguard_session" in test_client.cookies

    # Can access /api/auth/session immediately
    sess = test_client.get("/api/auth/session")
    assert sess.status_code == 200
    assert sess.json()["user"]["email"] == "demo-auditor@example.test"

    # User without institution sees empty institutions list and cannot access unauthorized institution records
    inst_resp = test_client.get("/api/institutions")
    assert inst_resp.status_code == 200
    assert inst_resp.json() == []

    # 4. Duplicate email rejected
    dup_resp = test_client.post("/api/auth/register", json={
        "email": "demo-auditor@example.test",
        "display_name": "Duplicate User",
        "password": "password6",
        "role": "reviewer",
    })
    assert dup_resp.status_code == 409


def test_system_admin_institution_lifecycle_and_assignment(client) -> None:
    test_client, _, session_factory = client
    test_client.cookies.clear()
    test_client.headers.pop("X-CSRF-Token", None)

    # 1. Sign in as system administrator
    admin_login = login(test_client, "admin@example.test")
    assert admin_login["user"]["system_admin"] is True

    # 2. Admin lists existing institutions
    initial_insts = test_client.get("/api/institutions").json()

    # 3. Admin creates new institution
    new_inst_name = "Synthetic Test University"
    new_inst = create_institution(test_client, new_inst_name)
    assert new_inst

    updated_insts = test_client.get("/api/institutions").json()
    assert any(inst["id"] == new_inst for inst in updated_insts)

    # 4. Register a new user without institution
    test_client.cookies.clear()
    test_client.headers.pop("X-CSRF-Token", None)
    new_user_reg = test_client.post("/api/auth/register", json={
        "email": "member-lifecycle@example.test",
        "display_name": "Member Lifecycle",
        "password": "validPass6",
        "role": "reviewer",
    }).json()
    new_user_id = new_user_reg["user"]["id"]

    # Newly registered user sees no institutions
    user_insts_before = test_client.get("/api/institutions").json()
    assert user_insts_before == []

    # 5. Sign back in as admin and assign user to the new institution
    login(test_client, "admin@example.test")
    assign_resp = test_client.put(
        f"/api/auth/users/{new_user_id}/memberships",
        json={"institution_id": new_inst, "role": "reviewer"},
    )
    assert assign_resp.status_code == 200
    assert any(m["institution_id"] == new_inst and m["role"] == "reviewer" for m in assign_resp.json()["memberships"])

    # 6. Sign in as the assigned member and verify the institution appears in their dropdown/list
    test_client.cookies.clear()
    test_client.headers.pop("X-CSRF-Token", None)
    member_login = test_client.post("/api/auth/login", json={"email": "member-lifecycle@example.test", "password": "validPass6"})
    assert member_login.status_code == 200
    test_client.headers["X-CSRF-Token"] = member_login.json()["csrf_token"]

    member_insts = test_client.get("/api/institutions").json()
    assert len(member_insts) == 1
    assert member_insts[0]["id"] == new_inst
    assert member_insts[0]["name"] == new_inst_name
