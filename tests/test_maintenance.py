def test_recommander_renvoie_501(client, auth_headers):
    response = client.post("/internal/ai/v1/maintenance/recommander", json={}, headers=auth_headers)
    assert response.status_code == 501
