import pytest
from logiflow_ai_service.app import create_app

@pytest.fixture
def client():
    """Crée un client de test Flask."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def api_key():
    """Clé API pour les tests."""
    return "logiflow-ai-secret-2026"