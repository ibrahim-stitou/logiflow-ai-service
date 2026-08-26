def test_copilot_ask_success(client, api_key):
    """Teste l'endpoint /copilot/ask avec une question valide."""
    response = client.post(
        '/internal/ai/v1/copilot/ask',
        json={"question": "Bonjour, comment ça va ?"},
        headers={"X-Internal-Api-Key": api_key}
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert "reponse" in data
    assert "modele" in data

def test_copilot_ask_no_question(client, api_key):
    """Teste l'endpoint sans question."""
    response = client.post(
        '/internal/ai/v1/copilot/ask',
        json={},
        headers={"X-Internal-Api-Key": api_key}
    )
    
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

def test_copilot_ask_no_api_key(client):
    """Teste l'endpoint sans clé API."""
    response = client.post(
        '/internal/ai/v1/copilot/ask',
        json={"question": "Bonjour"}
    )
    
    assert response.status_code == 401
    data = response.get_json()
    assert "error" in data