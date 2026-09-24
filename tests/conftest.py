import pytest

from logiflow_ai_service.app import create_app
from logiflow_ai_service.config import Settings
from tests.fakes import ConversationRepositoryMemoire

API_KEY = "test-api-key"
CALLBACK_KEY = "test-callback-key"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        internal_api_key=API_KEY,
        llm_base_url="http://llm.test/v1",
        llm_api_key="cle-test",
        llm_model="llama-3.3-70b-versatile",
        osrm_base_url="http://osrm.test",
        backend_base_url="http://backend.test",
        backend_callback_api_key=CALLBACK_KEY,
        copilote_titre_llm=False,
    )


@pytest.fixture
def repository() -> ConversationRepositoryMemoire:
    return ConversationRepositoryMemoire()


@pytest.fixture
def app(settings, repository):
    return create_app(settings, conversation_repository=repository)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"X-Internal-Api-Key": API_KEY}
