def test_route_protegee_sans_cle_renvoie_401(client):
    response = client.post("/internal/ai/v1/planification/proposer", json={"dossiers": []})
    assert response.status_code == 401


def test_route_protegee_avec_mauvaise_cle_renvoie_401(client):
    response = client.post(
        "/internal/ai/v1/planification/proposer",
        json={"dossiers": []},
        headers={"X-Internal-Api-Key": "mauvaise-cle"},
    )
    assert response.status_code == 401


def test_health_ne_necessite_pas_de_cle(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "UP"
