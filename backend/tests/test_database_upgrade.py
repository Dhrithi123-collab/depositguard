from sqlalchemy import inspect

from app.database.session import create_database_engine
from app.services import database


def test_phase3_upgrade_adds_nullable_policy_metadata_without_changing_audit_schema(tmp_path, monkeypatch):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE fdr_document_versions (id VARCHAR(36) PRIMARY KEY, storage_id VARCHAR(32))"
            )
            connection.exec_driver_sql(
                "CREATE TABLE audit_events (id VARCHAR(36) PRIMARY KEY, details JSON NOT NULL)"
            )
        monkeypatch.setattr(database, "engine", engine)

        database.upgrade_phase3_document_metadata()

        version_columns = {column["name"] for column in inspect(engine).get_columns("fdr_document_versions")}
        audit_columns = {column["name"] for column in inspect(engine).get_columns("audit_events")}
        assert {"upload_policy_version", "upload_policy_digest"}.issubset(version_columns)
        assert audit_columns == {"id", "details"}
    finally:
        engine.dispose()
