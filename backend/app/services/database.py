from sqlalchemy import inspect

from app.database.session import engine
from app.models import Base


def initialize_database() -> None:
    """Create tables for the local prototype; migrations belong to a later phase."""
    Base.metadata.create_all(bind=engine)
    upgrade_phase3_document_metadata()


def upgrade_phase3_document_metadata() -> None:
    """Add nullable metadata columns to the Phase 3 document-version table when upgrading it."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "fdr_document_versions" not in tables:
            return
        columns = {column["name"] for column in inspect(connection).get_columns("fdr_document_versions")}
        additions = {
            "upload_policy_version": "VARCHAR(80)",
            "upload_policy_digest": "VARCHAR(64)",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE fdr_document_versions ADD COLUMN {name} {sql_type}"
                )
