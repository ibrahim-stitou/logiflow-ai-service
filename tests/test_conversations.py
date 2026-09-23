import json

import httpx
import respx

BASE = "/internal/ai/v1/copilot"


def _headers(auth_headers, utilisateur="user-1"):
    return {**auth_headers, "X-Utilisateur-Id": utilisateur}


def _ndjson(*morceaux: dict) -> bytes:
    return "\n".join(json.dumps(m) for m in morceaux).encode()


def _evenements(corps: str) -> list[tuple[str, dict]]:
    evenements = []
    for bloc in corps.strip().split("\n\n"):
        lignes = dict(ligne.split(": ", 1) for ligne in bloc.splitlines())
        evenements.append((lignes["event"], json.loads(lignes["data"])))
    return evenements


def _creer(client, auth_headers, utilisateur="user-1", titre=None):
    response = client.post(
        f"{BASE}/conversations", json={"titre": titre}, headers=_headers(auth_headers, utilisateur)
    )
    assert response.status_code == 201
    return response.get_json()


def test_creer_puis_lister_ses_conversations(client, auth_headers):
    creee = _creer(client, auth_headers, titre="Voyages du jour")
    _creer(client, auth_headers, utilisateur="user-2")

    response = client.get(f"{BASE}/conversations", headers=_headers(auth_headers))

    assert response.status_code == 200
    assert [c["id"] for c in response.get_json()] == [creee["id"]]
    assert creee["titre"] == "Voyages du jour"
    assert "createdAt" in creee


def test_conversation_sans_titre_prend_le_titre_par_defaut(client, auth_headers):
    assert _creer(client, auth_headers)["titre"] == "Nouvelle conversation"


def test_conversation_d_un_autre_utilisateur_renvoie_404(client, auth_headers):
    creee = _creer(client, auth_headers, utilisateur="user-2")

    headers = _headers(auth_headers)
    url = f"{BASE}/conversations/{creee['id']}"
    assert client.get(url, headers=headers).status_code == 404
    assert client.patch(url, json={"titre": "x"}, headers=headers).status_code == 404
    assert client.delete(url, headers=headers).status_code == 404


def test_renommer_et_supprimer(client, auth_headers):
    creee = _creer(client, auth_headers)
    url = f"{BASE}/conversations/{creee['id']}"

    renommee = client.patch(url, json={"titre": "Carburant"}, headers=_headers(auth_headers))
    assert renommee.get_json()["titre"] == "Carburant"

    assert client.delete(url, headers=_headers(auth_headers)).status_code == 204
    assert client.get(url, headers=_headers(auth_headers)).status_code == 404


def test_en_tete_utilisateur_obligatoire(client, auth_headers):
    assert client.get(f"{BASE}/conversations", headers=auth_headers).status_code == 400


def test_cle_interne_obligatoire(client):
    response = client.get(f"{BASE}/conversations", headers={"X-Utilisateur-Id": "user-1"})
    assert response.status_code == 401


def test_renommer_avec_titre_vide_renvoie_400(client, auth_headers):
    creee = _creer(client, auth_headers)
    response = client.patch(
        f"{BASE}/conversations/{creee['id']}", json={"titre": ""}, headers=_headers(auth_headers)
    )
    assert response.status_code == 400


def _message(question="Bonjour", utilisateur="user-1"):
    return {
        "question": question,
        "utilisateur": {"id": utilisateur, "nom": "Alice", "roles": ["EXPLOITANT"]},
        "contexte": "jeton-123",
        "correlationId": "corr-1",
    }


def test_envoyer_un_message_streame_la_reponse_et_la_persiste(client, auth_headers, settings):
    creee = _creer(client, auth_headers)
    with respx.mock() as mock:
        mock.get(f"{settings.backend_base_url}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=[])
        )
        mock.post(f"{settings.ollama_base_url}/api/chat").mock(
            return_value=httpx.Response(
                200,
                content=_ndjson(
                    {"message": {"content": "Bon"}, "done": False},
                    {"message": {"content": "jour !"}, "done": False},
                    {"message": {"content": ""}, "done": True, "eval_count": 3},
                ),
            )
        )
        response = client.post(
            f"{BASE}/conversations/{creee['id']}/messages",
            json=_message(),
            headers=auth_headers,
        )
        corps = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    evenements = _evenements(corps)
    assert [nom for nom, _ in evenements] == ["meta", "token", "token", "titre", "fin"]
    assert "".join(d["texte"] for nom, d in evenements if nom == "token") == "Bonjour !"

    detail = client.get(
        f"{BASE}/conversations/{creee['id']}", headers=_headers(auth_headers)
    ).get_json()
    assert [(m["role"], m["contenu"], m["statut"]) for m in detail["messages"]] == [
        ("user", "Bonjour", "complet"),
        ("assistant", "Bonjour !", "complet"),
    ]
    assert detail["titre"] == "Bonjour"


def test_envoyer_dans_la_conversation_d_un_autre_renvoie_404(client, auth_headers):
    creee = _creer(client, auth_headers, utilisateur="user-2")
    response = client.post(
        f"{BASE}/conversations/{creee['id']}/messages", json=_message(), headers=auth_headers
    )
    assert response.status_code == 404


def test_envoyer_avec_contexte_manquant_renvoie_400(client, auth_headers):
    creee = _creer(client, auth_headers)
    corps = _message()
    del corps["contexte"]
    response = client.post(
        f"{BASE}/conversations/{creee['id']}/messages", json=corps, headers=auth_headers
    )
    assert response.status_code == 400


def test_feedback_sur_son_message(client, auth_headers, repository):
    from logiflow_ai_service.agents.copilot.model import Message, Role

    creee = _creer(client, auth_headers)
    message = repository.enregistrer_message(
        Message(
            conversation_id=__import__("uuid").UUID(creee["id"]), role=Role.ASSISTANT, contenu="x"
        )
    )
    url = f"{BASE}/messages/{message.id}/feedback"

    assert client.post(url, json={"note": 1}, headers=_headers(auth_headers)).status_code == 204
    assert (
        client.post(url, json={"note": 1}, headers=_headers(auth_headers, "user-2")).status_code
        == 404
    )
    assert client.post(url, json={"note": 5}, headers=_headers(auth_headers)).status_code == 400
    assert repository.feedbacks[message.id] == ("user-1", 1, None)
