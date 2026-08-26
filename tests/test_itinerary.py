def test_itinerary_calculer_success(client, api_key):
    """Teste l'endpoint /itinerary/calculer avec des coordonnées valides."""
    response = client.post(
        '/internal/ai/v1/itinerary/calculer',
        json={
            "origineLat": 33.5731,
            "origineLon": -7.5898,
            "destinationLat": 35.7595,
            "destinationLon": -5.8340
        },
        headers={"X-Internal-Api-Key": api_key}
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert "distanceKm" in data
    assert "dureeMin" in data

def test_itinerary_calculer_missing_fields(client, api_key):
    """Teste l'endpoint avec des champs manquants."""
    response = client.post(
        '/internal/ai/v1/itinerary/calculer',
        json={"origineLat": 33.5731},
        headers={"X-Internal-Api-Key": api_key}
    )
    
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data