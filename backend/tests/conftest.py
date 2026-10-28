import shutil
from pathlib import Path

import pytest
import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.routes import get_workflow_service
from app.database.session import Base, create_database_engine, get_db
from app.main import app
from app.api.routes import get_document_service
from app.api.routes import get_graph_service
from app.api.routes import get_priority_service
from app.services.documents import DocumentService
from app.services.storage import PrivateLocalStorage, UploadPolicyLoader
from app.services.workflow import WorkflowService
from app.services.graph import GraphService
from app.services.priority import PriorityScoringService
from app.services.auth import create_user


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(bind=database_engine)
    TestingSessionLocal = sessionmaker(bind=database_engine, autoflush=False, autocommit=False)

    config_path = tmp_path / "workflow.json"
    source_config = Path(__file__).resolve().parents[1] / "config" / "workflow.json"
    shutil.copyfile(source_config, config_path)

    def override_get_db():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workflow_service] = lambda: WorkflowService(config_path)
    graph_policy_path = tmp_path / "graph.json"
    source_graph = Path(__file__).resolve().parents[1] / "config" / "graph.json"
    shutil.copyfile(source_graph, graph_policy_path)
    app.dependency_overrides[get_graph_service] = lambda: GraphService(graph_policy_path)
    priority_policy_path = tmp_path / "priority.json"
    source_priority = Path(__file__).resolve().parents[1] / "config" / "priority.json"
    shutil.copyfile(source_priority, priority_policy_path)
    app.dependency_overrides[get_priority_service] = lambda: PriorityScoringService(
        priority_policy_path, WorkflowService(config_path),
    )
    with TestingSessionLocal() as setup_db:
        create_user(
            setup_db, email="admin@example.test", display_name="Test Administrator",
            password="synthetic-test-password", is_system_admin=True, must_change_password=False,
        )
        setup_db.commit()
    monkeypatch.setattr("app.main.initialize_database", lambda: None)
    try:
        with TestClient(app) as test_client:
            login = test_client.post("/api/auth/login", json={
                "email": "admin@example.test", "password": "synthetic-test-password",
            })
            assert login.status_code == 200
            test_client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
            yield test_client, config_path, TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=database_engine)
        database_engine.dispose()


@pytest.fixture
def upload_client(client, tmp_path: Path):
    test_client, config_path, session_factory = client
    policy_path = tmp_path / "uploads.json"
    source_policy = Path(__file__).resolve().parents[1] / "config" / "uploads.json"
    shutil.copyfile(source_policy, policy_path)
    storage = PrivateLocalStorage(tmp_path / "private-store")
    document_service = DocumentService(
        storage=storage,
        policy_loader=UploadPolicyLoader(policy_path),
        workflow=WorkflowService(config_path),
    )
    app.dependency_overrides[get_document_service] = lambda: document_service
    return test_client, session_factory, storage, policy_path
