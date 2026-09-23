"""Modèle du copilote conversationnel, indépendant de la persistance.

Les dataclasses ci-dessous circulent entre l'orchestrateur, le service et les repositories ; le
protocole `ConversationRepository` est implémenté en SQL (PostgreSQL `logiflow_ai`) en production
et en mémoire dans les tests.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID, uuid4


def maintenant() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    UTILISATEUR = "user"
    ASSISTANT = "assistant"


class StatutMessage(StrEnum):
    EN_COURS = "en_cours"
    COMPLET = "complet"
    INTERROMPU = "interrompu"
    ERREUR = "erreur"


@dataclass
class Conversation:
    utilisateur_id: str
    titre: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=maintenant)
    updated_at: datetime = field(default_factory=maintenant)


@dataclass
class Source:
    """Entité métier citée dans une réponse (lien cliquable côté frontend)."""

    type: str
    reference: str
    id: str | None = None

    def cle(self) -> tuple[str, str]:
        return (self.type, self.reference)

    def en_dict(self) -> dict[str, Any]:
        return {"type": self.type, "reference": self.reference, "id": self.id}


@dataclass
class Message:
    conversation_id: UUID
    role: Role
    contenu: str
    statut: StatutMessage = StatutMessage.COMPLET
    id: UUID = field(default_factory=uuid4)
    sources: list[Source] = field(default_factory=list)
    modele: str | None = None
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    duree_ms: int | None = None
    created_at: datetime = field(default_factory=maintenant)


@dataclass
class AppelOutil:
    message_id: UUID
    nom: str
    arguments: dict[str, Any]
    succes: bool
    duree_ms: int
    nb_resultats: int | None = None
    erreur: str | None = None
    id: UUID = field(default_factory=uuid4)


class ConversationRepository(Protocol):
    """Toute lecture/écriture est cloisonnée par `utilisateur_id` (transmis par Spring)."""

    def creer(self, conversation: Conversation) -> Conversation: ...

    def lister(self, utilisateur_id: str, limite: int, decalage: int) -> list[Conversation]: ...

    def obtenir(self, conversation_id: UUID, utilisateur_id: str) -> Conversation | None: ...

    def renommer(
        self, conversation_id: UUID, utilisateur_id: str, titre: str
    ) -> Conversation | None: ...

    def supprimer(self, conversation_id: UUID, utilisateur_id: str) -> bool: ...

    def enregistrer_message(self, message: Message) -> Message: ...

    def messages(self, conversation_id: UUID, limite: int | None = None) -> list[Message]:
        """Messages dans l'ordre chronologique ; avec `limite`, seulement les plus récents."""
        ...

    def enregistrer_appel_outil(self, appel: AppelOutil) -> None: ...

    def enregistrer_feedback(
        self, message_id: UUID, utilisateur_id: str, note: int, commentaire: str | None
    ) -> bool:
        """False si le message n'existe pas ou n'appartient pas à l'utilisateur."""
        ...


@dataclass(frozen=True)
class FragmentTrouve:
    source: str
    titre: str
    contenu: str
    score: float


class ConnaissanceRepository(Protocol):
    """Base de connaissance vectorielle (documentation fonctionnelle, procédures)."""

    def rechercher(self, embedding: list[float], limite: int) -> list[FragmentTrouve]: ...

    def remplacer_document(
        self, source: str, titre: str, fragments: list[tuple[str, list[float]]]
    ) -> None: ...
