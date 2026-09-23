import json
from datetime import date

import httpx
import pytest
import respx

from logiflow_ai_service.agents.copilot.model import (
    Conversation,
    FragmentTrouve,
    Message,
    Role,
    StatutMessage,
)
from logiflow_ai_service.agents.copilot.orchestrateur import CopiloteOrchestrateur
from logiflow_ai_service.agents.copilot.outils import BoiteOutils, ContexteAppel
from logiflow_ai_service.infrastructure.backend_client import BackendClient
from logiflow_ai_service.infrastructure.ollama_client import OllamaClient
from tests.fakes import ConnaissanceRepositoryMemoire, ConversationRepositoryMemoire

OLLAMA = "http://ollama.test"
BACKEND = "http://backend.test"

CATALOGUE = [
    {
        "nom": "rechercher_voyages",
        "libelle": "Recherche des voyages",
        "description": "Recherche des voyages",
        "parametres": {"type": "object", "properties": {"statut": {"type": "string"}}},
    }
]


def _ndjson(*morceaux: dict) -> httpx.Response:
    return httpx.Response(200, content="\n".join(json.dumps(m) for m in morceaux).encode())


def _texte(texte: str) -> httpx.Response:
    return _ndjson(
        {"message": {"content": texte}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 10, "eval_count": 5},
    )


def _appel_outil(nom: str, arguments) -> httpx.Response:
    return _ndjson(
        {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": nom, "arguments": arguments}}],
            },
            "done": False,
        },
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 7, "eval_count": 2},
    )


@pytest.fixture
def repository():
    return ConversationRepositoryMemoire()


@pytest.fixture
def conversation(repository):
    return repository.creer(Conversation(utilisateur_id="user-1", titre="Nouvelle conversation"))


@pytest.fixture
def contexte():
    return ContexteAppel(
        jeton="jeton-1", utilisateur_id="user-1", nom="Alice", roles=["EXPLOITANT"]
    )


def _orchestrateur(repository, connaissance=None, max_iterations=4, titre_llm=False):
    ollama = OllamaClient(OLLAMA, "llama3.1:8b", 5.0)
    return CopiloteOrchestrateur(
        repository,
        ollama,
        BoiteOutils(BackendClient(BACKEND, "cle-rappel", 5.0), ollama, connaissance),
        max_iterations_outils=max_iterations,
        historique_max=20,
        titre_llm=titre_llm,
        aujourd_hui=lambda: date(2026, 9, 23),
    )


def _assistant(repository) -> Message:
    [message] = [m for m in repository.messages_par_id.values() if m.role is Role.ASSISTANT]
    return message


def test_appel_d_outil_puis_reponse_avec_sources(repository, conversation, contexte):
    with respx.mock() as mock:
        catalogue = mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=CATALOGUE)
        )
        outil = mock.post(f"{BACKEND}/internal/copilote/outils/rechercher_voyages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "resultats": [{"reference": "VOY-2026-00003", "statut": "EN_COURS"}],
                    "total": 1,
                    "sources": [{"type": "VOYAGE", "reference": "VOY-2026-00003", "id": "v-3"}],
                },
            )
        )
        chat = mock.post(f"{OLLAMA}/api/chat").mock(
            side_effect=[
                _appel_outil("rechercher_voyages", {"statut": "EN_COURS"}),
                _texte("Un voyage en cours : VOY-2026-00003."),
            ]
        )

        evenements = list(_orchestrateur(repository).repondre(conversation, "Voyages ?", contexte))

    assert [nom for nom, _ in evenements] == [
        "meta",
        "outil",
        "outil",
        "token",
        "sources",
        "titre",
        "fin",
    ]
    assert evenements[1][1] == {
        "nom": "rechercher_voyages",
        "libelle": "Recherche des voyages",
        "statut": "debut",
    }
    assert evenements[4][1]["sources"] == [
        {"type": "VOYAGE", "reference": "VOY-2026-00003", "id": "v-3"}
    ]
    # Spring reçoit le secret de rappel et le jeton de contexte, jamais les rôles en clair.
    requete_outil = outil.calls.last.request
    assert requete_outil.headers["X-Internal-Api-Key"] == "cle-rappel"
    assert requete_outil.headers["X-Copilote-Contexte"] == "jeton-1"
    assert json.loads(requete_outil.content) == {"statut": "EN_COURS"}
    assert catalogue.call_count == 1
    # Le 2e appel au LLM contient le résultat de l'outil.
    second = json.loads(chat.calls[1].request.content)
    assert second["messages"][-1]["role"] == "tool"
    assert "VOY-2026-00003" in second["messages"][-1]["content"]
    assert second["messages"][0]["role"] == "system"
    assert "2026-09-23" in second["messages"][0]["content"]

    reponse = _assistant(repository)
    assert reponse.statut is StatutMessage.COMPLET
    assert reponse.contenu == "Un voyage en cours : VOY-2026-00003."
    assert reponse.tokens_completion == 7
    assert [s.reference for s in reponse.sources] == ["VOY-2026-00003"]
    [appel] = repository.appels_outils
    assert appel.succes and appel.nb_resultats == 1


def test_erreur_d_outil_renvoyee_au_llm(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=CATALOGUE)
        )
        mock.post(f"{BACKEND}/internal/copilote/outils/rechercher_voyages").mock(
            return_value=httpx.Response(400, json={"detail": "statut inconnu : XYZ"})
        )
        chat = mock.post(f"{OLLAMA}/api/chat").mock(
            side_effect=[
                _appel_outil("rechercher_voyages", '{"statut": "XYZ"}'),
                _texte("Statut invalide."),
            ]
        )
        evenements = list(_orchestrateur(repository).repondre(conversation, "?", contexte))

    assert (
        "outil",
        {"nom": "rechercher_voyages", "libelle": "Recherche des voyages", "statut": "erreur"},
    ) in evenements
    assert "statut inconnu" in json.loads(chat.calls[1].request.content)["messages"][-1]["content"]
    [appel] = repository.appels_outils
    assert not appel.succes and appel.arguments == {"statut": "XYZ"}


def test_outil_inconnu_n_est_pas_execute(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=CATALOGUE)
        )
        mock.post(f"{OLLAMA}/api/chat").mock(
            side_effect=[_appel_outil("supprimer_tout", {}), _texte("Désolé.")]
        )
        list(_orchestrateur(repository).repondre(conversation, "?", contexte))

    [appel] = repository.appels_outils
    assert not appel.succes and "Outil inconnu" in appel.erreur


def test_boucle_d_outils_bornee(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=CATALOGUE)
        )
        mock.post(f"{BACKEND}/internal/copilote/outils/rechercher_voyages").mock(
            return_value=httpx.Response(200, json={"resultats": [], "total": 0, "sources": []})
        )
        chat = mock.post(f"{OLLAMA}/api/chat").mock(
            side_effect=[
                _appel_outil("rechercher_voyages", {}),
                _appel_outil("rechercher_voyages", {}),
                _texte("Aucun voyage."),
            ]
        )
        list(_orchestrateur(repository, max_iterations=2).repondre(conversation, "?", contexte))

    assert chat.call_count == 3
    # Au dernier tour, les outils ne sont plus proposés : le LLM doit conclure.
    assert "tools" in json.loads(chat.calls[1].request.content)
    assert "tools" not in json.loads(chat.calls[2].request.content)


def test_catalogue_indisponible_repond_sans_outils(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            side_effect=httpx.ConnectError("refused")
        )
        chat = mock.post(f"{OLLAMA}/api/chat").mock(return_value=_texte("Bonjour."))
        evenements = list(_orchestrateur(repository).repondre(conversation, "Salut", contexte))

    assert evenements[-1][0] == "fin"
    corps = json.loads(chat.calls.last.request.content)
    assert "tools" not in corps
    assert "aucune donnée" in corps["messages"][0]["content"]


def test_ollama_indisponible_emet_une_erreur(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=[])
        )
        mock.post(f"{OLLAMA}/api/chat").mock(side_effect=httpx.ConnectError("refused"))
        evenements = list(_orchestrateur(repository).repondre(conversation, "?", contexte))

    assert [nom for nom, _ in evenements] == ["meta", "erreur"]
    assert evenements[1][1]["code"] == "LLM_INDISPONIBLE"
    assert _assistant(repository).statut is StatutMessage.ERREUR


def test_interruption_persiste_la_reponse_partielle(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=[])
        )
        mock.post(f"{OLLAMA}/api/chat").mock(
            return_value=_ndjson(
                {"message": {"content": "Début"}, "done": False},
                {"message": {"content": " suite"}, "done": False},
                {"message": {"content": ""}, "done": True},
            )
        )
        flux = _orchestrateur(repository).repondre(conversation, "?", contexte)
        assert next(flux)[0] == "meta"
        assert next(flux) == ("token", {"texte": "Début"})
        flux.close()  # le client a cliqué sur Stop

    reponse = _assistant(repository)
    assert reponse.statut is StatutMessage.INTERROMPU
    assert reponse.contenu == "Début"


def test_historique_transmis_au_llm(repository, conversation, contexte):
    repository.enregistrer_message(
        Message(conversation_id=conversation.id, role=Role.UTILISATEUR, contenu="Question 1")
    )
    repository.enregistrer_message(
        Message(conversation_id=conversation.id, role=Role.ASSISTANT, contenu="Réponse 1")
    )
    repository.enregistrer_message(
        Message(
            conversation_id=conversation.id,
            role=Role.ASSISTANT,
            contenu="partiel",
            statut=StatutMessage.INTERROMPU,
        )
    )
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=[])
        )
        chat = mock.post(f"{OLLAMA}/api/chat").mock(return_value=_texte("Réponse 2"))
        evenements = list(_orchestrateur(repository).repondre(conversation, "Question 2", contexte))

    messages = json.loads(chat.calls.last.request.content)["messages"]
    assert [(m["role"], m["content"]) for m in messages[1:]] == [
        ("user", "Question 1"),
        ("assistant", "Réponse 1"),
        ("user", "Question 2"),
    ]
    # Pas de nouveau titre : ce n'est pas le premier échange.
    assert "titre" not in [nom for nom, _ in evenements]


def test_titre_genere_par_le_llm(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=[])
        )
        mock.post(f"{OLLAMA}/api/chat").mock(
            side_effect=[
                _texte("Réponse"),
                httpx.Response(200, json={"message": {"content": "« Consommation carburant »"}}),
            ]
        )
        evenements = list(
            _orchestrateur(repository, titre_llm=True).repondre(conversation, "?", contexte)
        )

    assert ("titre", {"titre": "Consommation carburant"}) in evenements
    assert conversation.titre == "Consommation carburant"


def test_outil_local_base_de_connaissance(repository, conversation, contexte):
    connaissance = ConnaissanceRepositoryMemoire(
        [FragmentTrouve("guide.html", "Guide", "Pour créer un dossier, ...", 0.91)]
    )
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            return_value=httpx.Response(200, json=[])
        )
        mock.post(f"{OLLAMA}/api/embed").mock(
            return_value=httpx.Response(200, json={"embeddings": [[0.1] * 768]})
        )
        chat = mock.post(f"{OLLAMA}/api/chat").mock(
            side_effect=[
                _appel_outil("rechercher_base_connaissance", {"question": "créer un dossier"}),
                _texte("Voici comment faire."),
            ]
        )
        list(_orchestrateur(repository, connaissance).repondre(conversation, "?", contexte))

    premier = json.loads(chat.calls[0].request.content)
    assert [t["function"]["name"] for t in premier["tools"]] == ["rechercher_base_connaissance"]
    assert (
        "Pour créer un dossier"
        in json.loads(chat.calls[1].request.content)["messages"][-1]["content"]
    )
