"""Agent copilote conversationnel.

- `CopiloteService` : ancienne question/réponse unique (route /copilot/ask), conservée le temps
  que le frontend migre vers les conversations.
- `ConversationService` : conversations persistées dans la base propre du service IA ; la
  génération des réponses est déléguée à `CopiloteOrchestrateur` (LLM + outils, streaming).
"""

from collections.abc import Iterator
from uuid import UUID

from logiflow_ai_service.agents.copilot.model import (
    Conversation,
    ConversationRepository,
    Message,
)
from logiflow_ai_service.agents.copilot.orchestrateur import (
    TITRE_PAR_DEFAUT,
    CopiloteOrchestrateur,
    Evenement,
)
from logiflow_ai_service.agents.copilot.outils import ContexteAppel
from logiflow_ai_service.agents.copilot.prompts import PROMPT_QUESTION_UNIQUE
from logiflow_ai_service.agents.copilot.schemas import CopilotAskRequest, CopilotAskResponse
from logiflow_ai_service.infrastructure.llm_client import LlmClient

_CONFIANCE_PAR_DEFAUT = 0.5


class CopiloteService:
    def __init__(self, llm_client: LlmClient) -> None:
        self._llm_client = llm_client

    def repondre(self, request: CopilotAskRequest) -> CopilotAskResponse:
        contenu = self._llm_client.chat(PROMPT_QUESTION_UNIQUE, request.question)
        return CopilotAskResponse(
            reponse=contenu,
            sources=[],
            confiance=_CONFIANCE_PAR_DEFAUT,
        )


class ConversationIntrouvable(Exception):
    """Conversation absente OU appartenant à un autre utilisateur (indistinguables : 404)."""


class ConversationService:
    def __init__(
        self, repository: ConversationRepository, orchestrateur: CopiloteOrchestrateur
    ) -> None:
        self._repository = repository
        self._orchestrateur = orchestrateur

    def creer(self, utilisateur_id: str, titre: str | None) -> Conversation:
        return self._repository.creer(
            Conversation(
                utilisateur_id=utilisateur_id, titre=(titre or "").strip() or TITRE_PAR_DEFAUT
            )
        )

    def lister(self, utilisateur_id: str, limite: int, decalage: int) -> list[Conversation]:
        return self._repository.lister(utilisateur_id, limite, decalage)

    def obtenir(self, conversation_id: UUID, utilisateur_id: str) -> Conversation:
        conversation = self._repository.obtenir(conversation_id, utilisateur_id)
        if conversation is None:
            raise ConversationIntrouvable()
        return conversation

    def messages(self, conversation_id: UUID, utilisateur_id: str) -> list[Message]:
        self.obtenir(conversation_id, utilisateur_id)
        return self._repository.messages(conversation_id)

    def renommer(self, conversation_id: UUID, utilisateur_id: str, titre: str) -> Conversation:
        conversation = self._repository.renommer(conversation_id, utilisateur_id, titre.strip())
        if conversation is None:
            raise ConversationIntrouvable()
        return conversation

    def supprimer(self, conversation_id: UUID, utilisateur_id: str) -> None:
        if not self._repository.supprimer(conversation_id, utilisateur_id):
            raise ConversationIntrouvable()

    def noter(
        self, message_id: UUID, utilisateur_id: str, note: int, commentaire: str | None
    ) -> None:
        if not self._repository.enregistrer_feedback(message_id, utilisateur_id, note, commentaire):
            raise ConversationIntrouvable()

    def envoyer(
        self, conversation_id: UUID, question: str, contexte: ContexteAppel
    ) -> Iterator[Evenement]:
        """Vérifie l'appartenance AVANT d'ouvrir le flux (404 propre), puis délègue."""
        conversation = self.obtenir(conversation_id, contexte.utilisateur_id)
        return self._orchestrateur.repondre(conversation, question, contexte)
