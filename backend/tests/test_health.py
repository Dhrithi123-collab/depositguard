import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_health_endpoint_reports_api_process_status(client) -> None:
    test_client, _, _ = client
    response = test_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_uses_standard_error_envelope(client) -> None:
    test_client, _, _ = client
    response = test_client.get("/api/not-a-route")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "http_error", "message": "Not Found"}}


def test_api_prefix_configuration_rejects_root_path() -> None:
    with pytest.raises(ValidationError):
        Settings(api_v1_prefix="/")


def test_settings_accept_json_cors_origin_list() -> None:
    settings = Settings(cors_origins=["http://localhost:5173"])

    assert settings.cors_origins == ["http://localhost:5173"]
