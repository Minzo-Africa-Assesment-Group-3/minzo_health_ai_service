from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "minzo-express-ai"}


def test_swagger_and_streaming_endpoint_are_exposed() -> None:
    with TestClient(app) as client:
        docs_response = client.get("/docs")
        openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert openapi_response.status_code == 200
    paths = openapi_response.json()["paths"]
    assert "/v1/assistant/messages" in paths
    assert "/v1/assistant/messages/stream" in paths
    assert "/v1/moderation/customer-reviews/evaluate" in paths
