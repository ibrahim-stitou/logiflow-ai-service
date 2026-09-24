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
from logiflow_ai_service.infrastructure.llm_client import LlmClient
from tests.fakes import ConnaissanceRepositoryMemoire, ConversationRepositoryMemoire
from tests.llm_mock import CHAT, LLM, appel_outil, reponse_chat, sse, texte

BACKEND = "http://backend.test"

CATALOGUE = [
    {
        "nom": "rechercher_voyages",
        "libelle": "Recherche des voyages",
        "description": "Recherche des voyages",
        "parametres": {"type": "object", "properties": {"statut": {"type": "string"}}},
    }
]


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
    llm = LlmClient(LLM, "cle-test", "openai/gpt-oss-120b", 5.0, embed_model="modele-embed")
    return CopiloteOrchestrateur(
        repository,
        llm,
        BoiteOutils(BackendClient(BACKEND, "cle-rappel", 5.0), llm, connaissance),
        max_iterations_outils=max_iterations,
        historique_max=20,
        titre_llm=titre_llm,
        aujourd_hui=lambda: date(2026, 9, 23),
    )


def _assistant(repository) -> Message:
    [message] = [m for m in repository.messages_par_id.values() if m.role is Role.ASSISTANT]
    return message


def _catalogue(mock, catalogue=CATALOGUE):
    return mock.get(f"{BACKEND}/internal/copilote/outils").mock(
        return_value=httpx.Response(200, json=catalogue)
    )


def test_appel_d_outil_puis_reponse_avec_sources(repository, conversation, contexte):
    with respx.mock() as mock:
        catalogue = _catalogue(mock)
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
        chat = mock.post(CHAT).mock(
            side_effect=[
                appel_outil("rechercher_voyages", {"statut": "EN_COURS"}, "call_42"),
                texte("Un voyage en cours : ", "VOY-2026-00003."),
            ]
        )

        evenements = list(_orchestrateur(repository).repondre(conversation, "Voyages ?", contexte))

    assert [nom for nom, _ in evenements] == [
        "meta",
        "outil",
        "outil",
        "token",
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
    assert evenements[5][1]["sources"] == [
        {"type": "VOYAGE", "reference": "VOY-2026-00003", "id": "v-3"}
    ]
    # Spring reçoit le secret de rappel et le jeton de contexte, jamais les rôles en clair.
    requete_outil = outil.calls.last.request
    assert requete_outil.headers["X-Internal-Api-Key"] == "cle-rappel"
    assert requete_outil.headers["X-Copilote-Contexte"] == "jeton-1"
    # Arguments reçus en deux morceaux dans le flux, réassemblés.
    assert json.loads(requete_outil.content) == {"statut": "EN_COURS"}
    assert catalogue.call_count == 1

    premier = json.loads(chat.calls[0].request.content)
    assert chat.calls[0].request.headers["Authorization"] == "Bearer cle-test"
    assert premier["model"] == "openai/gpt-oss-120b"
    assert premier["stream"] is True
    assert premier["tool_choice"] == "auto"
    assert [t["function"]["name"] for t in premier["tools"]] == ["rechercher_voyages"]
    # Le 2e appel au LLM contient l'appel d'outil (format OpenAI) puis son résultat.
    second = json.loads(chat.calls[1].request.content)
    appel_assistant, resultat = second["messages"][-2:]
    assert appel_assistant["tool_calls"][0]["id"] == "call_42"
    assert json.loads(appel_assistant["tool_calls"][0]["function"]["arguments"]) == {
        "statut": "EN_COURS"
    }
    assert resultat["role"] == "tool"
    assert resultat["tool_call_id"] == "call_42"
    assert "VOY-2026-00003" in resultat["content"]
    assert second["messages"][0]["role"] == "system"
    assert "2026-09-23" in second["messages"][0]["content"]

    reponse = _assistant(repository)
    assert reponse.statut is StatutMessage.COMPLET
    assert reponse.contenu == "Un voyage en cours : VOY-2026-00003."
    assert reponse.modele == "openai/gpt-oss-120b"
    assert (reponse.tokens_prompt, reponse.tokens_completion) == (17, 7)
    assert [s.reference for s in reponse.sources] == ["VOY-2026-00003"]
    [appel] = repository.appels_outils
    assert appel.succes and appel.nb_resultats == 1


def test_erreur_d_outil_renvoyee_au_llm(repository, conversation, contexte):
    with respx.mock() as mock:
        _catalogue(mock)
        mock.post(f"{BACKEND}/internal/copilote/outils/rechercher_voyages").mock(
            return_value=httpx.Response(400, json={"detail": "statut inconnu : XYZ"})
        )
        chat = mock.post(CHAT).mock(
            side_effect=[
                appel_outil("rechercher_voyages", {"statut": "XYZ"}),
                texte("Statut invalide."),
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
        _catalogue(mock)
        mock.post(CHAT).mock(side_effect=[appel_outil("supprimer_tout", {}), texte("Désolé.")])
        list(_orchestrateur(repository).repondre(conversation, "?", contexte))

    [appel] = repository.appels_outils
    assert not appel.succes and "Outil inconnu" in appel.erreur


def test_boucle_d_outils_bornee(repository, conversation, contexte):
    with respx.mock() as mock:
        _catalogue(mock)
        mock.post(f"{BACKEND}/internal/copilote/outils/rechercher_voyages").mock(
            return_value=httpx.Response(200, json={"resultats": [], "total": 0, "sources": []})
        )
        chat = mock.post(CHAT).mock(
            side_effect=[
                appel_outil("rechercher_voyages", {}),
                appel_outil("rechercher_voyages", {}, "call_2"),
                texte("Aucun voyage."),
            ]
        )
        list(_orchestrateur(repository, max_iterations=2).repondre(conversation, "?", contexte))

    assert chat.call_count == 3
    # Au dernier tour, plus d'appel d'outil possible : le LLM doit conclure.
    assert json.loads(chat.calls[1].request.content)["tool_choice"] == "auto"
    assert json.loads(chat.calls[2].request.content)["tool_choice"] == "none"


def test_catalogue_indisponible_repond_sans_outils(repository, conversation, contexte):
    with respx.mock() as mock:
        mock.get(f"{BACKEND}/internal/copilote/outils").mock(
            side_effect=httpx.ConnectError("refused")
        )
        chat = mock.post(CHAT).mock(return_value=texte("Bonjour."))
        evenements = list(_orchestrateur(repository).repondre(conversation, "Salut", contexte))

    assert evenements[-1][0] == "fin"
    corps = json.loads(chat.calls.last.request.content)
    assert "tools" not in corps
    assert "aucune donnée" in corps["messages"][0]["content"]


def test_llm_indisponible_emet_une_erreur(repository, conversation, contexte):
    with respx.mock() as mock:
        _catalogue(mock, [])
        mock.post(CHAT).mock(side_effect=httpx.ConnectError("refused"))
        evenements = list(_orchestrateur(repository).repondre(conversation, "?", contexte))

    assert [nom for nom, _ in evenements] == ["meta", "erreur"]
    assert evenements[1][1]["code"] == "LLM_INDISPONIBLE"
    assert _assistant(repository).statut is StatutMessage.ERREUR


def test_quota_atteint_emet_une_erreur_explicite(repository, conversation, contexte):
    with respx.mock() as mock:
        _catalogue(mock, [])
        mock.post(CHAT).mock(
            return_value=httpx.Response(
                429, json={"error": {"message": "Rate limit reached for model"}}
            )
        )
        evenements = list(_orchestrateur(repository).repondre(conversation, "?", contexte))

    assert evenements[-1][0] == "erreur"
    assert evenements[-1][1]["code"] == "QUOTA_LLM"
    assert "Quota" in evenements[-1][1]["message"]


def test_interruption_persiste_la_reponse_partielle(repository, conversation, contexte):
    with respx.mock() as mock:
        _catalogue(mock, [])
        mock.post(CHAT).mock(return_value=texte("Début", " suite"))
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
        _catalogue(mock, [])
        chat = mock.post(CHAT).mock(return_value=texte("Réponse 2"))
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
        _catalogue(mock, [])
        mock.post(CHAT).mock(
            side_effect=[texte("Réponse"), reponse_chat("« Consommation carburant »")]
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
        _catalogue(mock, [])
        embed = mock.post(f"{LLM}/embeddings").mock(
            return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1] * 8}]})
        )
        chat = mock.post(CHAT).mock(
            side_effect=[
                appel_outil("rechercher_base_connaissance", {"question": "créer un dossier"}),
                texte("Voici comment faire."),
            ]
        )
        list(_orchestrateur(repository, connaissance).repondre(conversation, "?", contexte))

    assert json.loads(embed.calls.last.request.content)["model"] == "modele-embed"
    premier = json.loads(chat.calls[0].request.content)
    assert [t["function"]["name"] for t in premier["tools"]] == ["rechercher_base_connaissance"]
    assert (
        "Pour créer un dossier"
        in json.loads(chat.calls[1].request.content)["messages"][-1]["content"]
    )


def test_erreur_du_fournisseur_dans_le_flux(repository, conversation, contexte):
    with respx.mock() as mock:
        _catalogue(mock, [])
        mock.post(CHAT).mock(return_value=sse({"error": {"message": "model overloaded"}}))
        evenements = list(_orchestrateur(repository).repondre(conversation, "?", contexte))

    assert evenements[-1] == (
        "erreur",
        {
            "code": "LLM_INDISPONIBLE",
            "message": "Le moteur IA est momentanément indisponible. Réessayez plus tard.",
        },
    )
