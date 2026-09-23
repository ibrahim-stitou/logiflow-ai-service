"""Schémas du contrat du copilote (voir docs/integration-ia.md côté backend)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from logiflow_ai_service.agents.copilot.model import Conversation, Message
from logiflow_ai_service.schemas import CamelModel


class Utilisateur(CamelModel):
    id: str
    roles: list[str] = Field(default_factory=list)


class CopilotAskRequest(CamelModel):
    question: str
    utilisateur: Utilisateur
    correlation_id: str | None = None


class CopilotAskResponse(CamelModel):
    reponse: str
    sources: list[str] = Field(default_factory=list)
    confiance: float | None = None


# --- Conversations (chatbot) -------------------------------------------------------------------


class UtilisateurMessage(CamelModel):
    id: str = Field(min_length=1, max_length=255)
    nom: str = Field(default="", max_length=255)
    roles: list[str] = Field(default_factory=list)


class EnvoyerMessageRequest(CamelModel):
    question: str = Field(min_length=1, max_length=4000)
    utilisateur: UtilisateurMessage
    # Jeton opaque émis par Spring pour ce message, renvoyé à chaque appel d'outil.
    contexte: str = Field(min_length=1, max_length=200)
    correlation_id: str | None = None


class CreerConversationRequest(CamelModel):
    titre: str | None = Field(default=None, max_length=200)


class RenommerConversationRequest(CamelModel):
    titre: str = Field(min_length=1, max_length=200)


class FeedbackRequest(CamelModel):
    note: Literal[-1, 1]
    commentaire: str | None = Field(default=None, max_length=2000)


class SourceDto(CamelModel):
    type: str
    reference: str
    id: str | None = None


class MessageDto(CamelModel):
    id: UUID
    role: str
    contenu: str
    statut: str
    sources: list[SourceDto]
    created_at: datetime

    @classmethod
    def depuis(cls, message: Message) -> "MessageDto":
        return cls(
            id=message.id,
            role=message.role.value,
            contenu=message.contenu,
            statut=message.statut.value,
            sources=[SourceDto(**s.en_dict()) for s in message.sources],
            created_at=message.created_at,
        )


class ConversationDto(CamelModel):
    id: UUID
    titre: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def depuis(cls, conversation: Conversation) -> "ConversationDto":
        return cls(
            id=conversation.id,
            titre=conversation.titre,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationDetailDto(ConversationDto):
    messages: list[MessageDto]
