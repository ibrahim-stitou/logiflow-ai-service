def test_maintenance_recommander_success(client, api_key):
    """Teste l'endpoint /maintenance/recommander avec un véhicule valide."""
    response = client.post(
        '/internal/ai/v1/maintenance/recommander',
        json={
            "vehicule": {
                "id": "12345",
                "kmDepuisVidange": 5000,
                "kmDepuisFreins": 10000,
                "kmDepuisPneus": 15000,
                "dateVisiteTechnique": "2026-01-01",
                "ageAns": 5,
                "nbPannes": 1
            }
        },
        headers={"X-Internal-Api-Key": api_key}
    )

    assert response.status_code == 200
    data = response.get_json()
    assert "score" in data
    assert "statut" in data
    assert "recommandations" in data
    assert 0 <= data["score"] <= 100


def test_maintenance_recommander_no_vehicule(client, api_key):
    """Teste l'endpoint sans vehicule."""
    response = client.post(
        '/internal/ai/v1/maintenance/recommander',
        json={},
        headers={"X-Internal-Api-Key": api_key}
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data