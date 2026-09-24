import httpx
import pytest
import respx

MODELES = {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "llama-3.1-8b-instant"}]}


@pytest.mark.parametrize(
    ("reponse_models", "attendu"),
    [
        (httpx.Response(200, json=MODELES), "UP"),
        (httpx.Response(200, json={"data": [{"id": "autre-modele"}]}), "MODELE_ABSENT"),
        (httpx.Response(401, json={"error": {"message": "Invalid API Key"}}), "CLE_INVALIDE"),
        (httpx.ConnectError("refused"), "DOWN"),
    ],
)
def test_health_detaille_l_etat_du_llm(client, settings, reponse_models, attendu):
    with respx.mock(base_url=settings.llm_base_url) as mock:
        route = mock.get("/models")
        if isinstance(reponse_models, Exception):
            route.mock(side_effect=reponse_models)
        else:
            route.mock(return_value=reponse_models)
        corps = client.get("/health").get_json()

    assert corps["status"] == "UP"
    assert corps["dependances"]["llm"] == attendu
    assert corps["modele"] == "llama-3.3-70b-versatile"
    assert corps["fournisseur"] == "llm.test"


def test_health_sans_cle_api(settings, repository):
    from logiflow_ai_service.app import create_app

    app = create_app(
        settings.model_copy(update={"llm_api_key": ""}), conversation_repository=repository
    )
    corps = app.test_client().get("/health").get_json()

    assert corps["dependances"]["llm"] == "CLE_ABSENTE"
