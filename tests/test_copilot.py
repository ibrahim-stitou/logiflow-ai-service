import httpx
import respx


def test_ask_renvoie_la_reponse_du_llm(client, settings, auth_headers):
    with respx.mock(base_url=settings.ollama_base_url) as mock:
        mock.post("/api/chat").mock(
            return_value=httpx.Response(
                200, json={"message": {"content": "3 véhicules disponibles"}}
            )
        )
        payload = {
            "question": "Quels camions sont libres demain ?",
            "utilisateur": {"id": "user-1", "roles": ["EXPLOITANT"]},
            "correlationId": "corr-1",
        }
        response = client.post("/internal/ai/v1/copilot/ask", json=payload, headers=auth_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["reponse"] == "3 véhicules disponibles"
    assert body["sources"] == []
    assert body["confiance"] is not None


def test_ask_renvoie_503_si_ollama_indisponible(client, settings, auth_headers):
    with respx.mock(base_url=settings.ollama_base_url) as mock:
        mock.post("/api/chat").mock(side_effect=httpx.ConnectError("connection refused"))
        payload = {
            "question": "Question",
            "utilisateur": {"id": "user-1", "roles": []},
        }
        response = client.post("/internal/ai/v1/copilot/ask", json=payload, headers=auth_headers)

    assert response.status_code == 503


def test_ask_avec_corps_invalide_renvoie_400(client, auth_headers):
    response = client.post("/internal/ai/v1/copilot/ask", json={}, headers=auth_headers)
    assert response.status_code == 400
