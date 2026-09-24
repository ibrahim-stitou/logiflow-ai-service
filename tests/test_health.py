import httpx
import pytest
import respx


@pytest.mark.parametrize(
    ("reponse_tags", "attendu"),
    [
        (httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}]}), "UP"),
        (httpx.Response(200, json={"models": [{"name": "mistral:latest"}]}), "MODELE_ABSENT"),
        (httpx.ConnectError("refused"), "DOWN"),
    ],
)
def test_health_detaille_l_etat_d_ollama(client, settings, reponse_tags, attendu):
    with respx.mock(base_url=settings.ollama_base_url) as mock:
        route = mock.get("/api/tags")
        if isinstance(reponse_tags, Exception):
            route.mock(side_effect=reponse_tags)
        else:
            route.mock(return_value=reponse_tags)
        corps = client.get("/health").get_json()

    assert corps["status"] == "UP"
    assert corps["dependances"]["ollama"] == attendu
    assert corps["modele"] == settings.ollama_model
