import pytest

from logiflow_ai_service.app import create_app
from logiflow_ai_service.config import Settings

API_KEY = "test-api-key"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        internal_api_key=API_KEY,
        ollama_base_url="http://ollama.test",
        osrm_base_url="http://osrm.test",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"X-Internal-Api-Key": API_KEY}
