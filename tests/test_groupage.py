def test_groupage_analyser_success(client, api_key):
    """Teste l'endpoint /groupage/analyser avec des candidats valides."""
    response = client.post(
        '/internal/ai/v1/groupage/analyser',
        json={
            "candidats": [
                {
                    "id": "1111",
                    "reference": "DT-001",
                    "poidsBrutKg": 1500.5,
                    "volumeM3": 12.0,
                    "nbPalettes": 4,
                    "contientAdr": False,
                    "groupable": True,
                    "siteChargementLat": 33.5731,
                    "siteChargementLon": -7.5898,
                    "dateDechargement": "2026-08-26",
                    "carrosserieRequise": "PLATEAU"
                },
                {
                    "id": "2222",
                    "reference": "DT-002",
                    "poidsBrutKg": 800.0,
                    "volumeM3": 8.0,
                    "nbPalettes": 2,
                    "contientAdr": False,
                    "groupable": True,
                    "siteChargementLat": 33.5731,
                    "siteChargementLon": -7.5898,
                    "dateDechargement": "2026-08-27",
                    "carrosserieRequise": "PLATEAU"
                }
            ]
        },
        headers={"X-Internal-Api-Key": api_key}
    )

    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    proposition = data[0]
    assert "score" in proposition
    assert "justification" in proposition