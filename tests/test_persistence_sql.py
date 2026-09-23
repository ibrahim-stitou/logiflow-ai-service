"""Tests des repositories SQL sur un vrai PostgreSQL + pgvector.

Ignorés sans `TEST_DATABASE_URL` (ex. postgresql+psycopg://logiflow_ai:...@localhost:5433/logiflow_ai_test).
La base est migrée (Alembic) puis vidée avant chaque test.
"""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from logiflow_ai_service.agents.copilot.model import (
    AppelOutil,
    Conversation,
    Message,
    Role,
    Source,
    StatutMessage,
)
from logiflow_ai_service.config import get_settings
from logiflow_ai_service.infrastructure.db import creer_engine, creer_session_factory
from logiflow_ai_service.infrastructure.persistence.connaissance_repository import (
    SqlConnaissanceRepository,
)
from logiflow_ai_service.infrastructure.persistence.conversation_repository import (
    SqlConversationRepository,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL non défini")


@pytest.fixture(scope="module")
def session_factory():
    os.environ["DATABASE_URL"] = URL
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = creer_engine(URL)
    yield creer_session_factory(engine)
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def vider(session_factory):
    with session_factory.begin() as session:
        session.execute(
            text("TRUNCATE copilote.conversation, copilote.document_connaissance CASCADE")
        )


def test_cycle_de_vie_d_une_conversation(session_factory):
    repo = SqlConversationRepository(session_factory)
    conversation = repo.creer(Conversation(utilisateur_id="u1", titre="Test"))
    repo.creer(Conversation(utilisateur_id="u2", titre="Autre"))

    question = repo.enregistrer_message(
        Message(conversation_id=conversation.id, role=Role.UTILISATEUR, contenu="Q")
    )
    reponse = repo.enregistrer_message(
        Message(
            conversation_id=conversation.id,
            role=Role.ASSISTANT,
            contenu="R",
            statut=StatutMessage.EN_COURS,
            sources=[Source("VOYAGE", "VOY-1", "id-1")],
        )
    )
    reponse.contenu = "Réponse finale"
    reponse.statut = StatutMessage.COMPLET
    repo.enregistrer_message(reponse)  # mise à jour (merge)
    repo.enregistrer_appel_outil(
        AppelOutil(message_id=reponse.id, nom="x", arguments={"a": 1}, succes=True, duree_ms=3)
    )

    assert [c.titre for c in repo.lister("u1", 10, 0)] == ["Test"]
    assert repo.obtenir(conversation.id, "u2") is None
    messages = repo.messages(conversation.id)
    assert [m.id for m in messages] == [question.id, reponse.id]
    assert messages[1].contenu == "Réponse finale"
    assert messages[1].sources == [Source("VOYAGE", "VOY-1", "id-1")]
    assert [m.id for m in repo.messages(conversation.id, limite=1)] == [reponse.id]

    assert repo.enregistrer_feedback(reponse.id, "u1", 1, None)
    assert not repo.enregistrer_feedback(reponse.id, "u2", 1, None)
    assert not repo.enregistrer_feedback(uuid4(), "u1", 1, None)

    assert repo.renommer(conversation.id, "u1", "Renommée").titre == "Renommée"
    assert not repo.supprimer(conversation.id, "u2")
    assert repo.supprimer(conversation.id, "u1")
    assert repo.messages(conversation.id) == []


def test_recherche_vectorielle(session_factory):
    repo = SqlConnaissanceRepository(session_factory)
    proche = [1.0] + [0.0] * 767
    loin = [0.0] * 767 + [1.0]
    repo.remplacer_document("guide.md", "Guide", [("proche", proche), ("loin", loin)])
    repo.remplacer_document("guide.md", "Guide v2", [("proche v2", proche), ("loin v2", loin)])

    resultats = repo.rechercher(proche, limite=1)

    assert [(r.titre, r.contenu) for r in resultats] == [("Guide v2", "proche v2")]
    assert resultats[0].score == pytest.approx(1.0)
