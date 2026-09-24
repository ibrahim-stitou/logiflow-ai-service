"""Doubles de test : repositories en mémoire (même contrat que les implémentations SQL)."""

from uuid import UUID

from logiflow_ai_service.agents.copilot.model import (
    AppelOutil,
    Conversation,
    FragmentTrouve,
    Message,
    maintenant,
)


class ConversationRepositoryMemoire:
    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.messages_par_id: dict[UUID, Message] = {}
        self.appels_outils: list[AppelOutil] = []
        self.feedbacks: dict[UUID, tuple[str, int, str | None]] = {}

    def creer(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.id] = conversation
        return conversation

    def lister(self, utilisateur_id: str, limite: int, decalage: int) -> list[Conversation]:
        a_moi = [c for c in self.conversations.values() if c.utilisateur_id == utilisateur_id]
        a_moi.sort(key=lambda c: c.updated_at, reverse=True)
        return a_moi[decalage : decalage + limite]

    def obtenir(self, conversation_id: UUID, utilisateur_id: str) -> Conversation | None:
        conversation = self.conversations.get(conversation_id)
        if conversation is None or conversation.utilisateur_id != utilisateur_id:
            return None
        return conversation

    def renommer(self, conversation_id: UUID, utilisateur_id: str, titre: str):
        conversation = self.obtenir(conversation_id, utilisateur_id)
        if conversation is not None:
            conversation.titre = titre
        return conversation

    def supprimer(self, conversation_id: UUID, utilisateur_id: str) -> bool:
        if self.obtenir(conversation_id, utilisateur_id) is None:
            return False
        del self.conversations[conversation_id]
        return True

    def enregistrer_message(self, message: Message) -> Message:
        self.messages_par_id[message.id] = message
        if conversation := self.conversations.get(message.conversation_id):
            conversation.updated_at = maintenant()
        return message

    def messages(self, conversation_id: UUID, limite: int | None = None) -> list[Message]:
        messages = sorted(
            (m for m in self.messages_par_id.values() if m.conversation_id == conversation_id),
            key=lambda m: m.created_at,
        )
        return messages[-limite:] if limite else messages

    def enregistrer_appel_outil(self, appel: AppelOutil) -> None:
        # Même contrainte que la clé étrangère appel_outil.message_id en base.
        if appel.message_id not in self.messages_par_id:
            raise AssertionError(f"message {appel.message_id} non persisté (clé étrangère)")
        self.appels_outils.append(appel)

    def enregistrer_feedback(self, message_id, utilisateur_id, note, commentaire) -> bool:
        message = self.messages_par_id.get(message_id)
        if message is None or self.obtenir(message.conversation_id, utilisateur_id) is None:
            return False
        self.feedbacks[message_id] = (utilisateur_id, note, commentaire)
        return True


class ConnaissanceRepositoryMemoire:
    def __init__(self, fragments: list[FragmentTrouve] | None = None) -> None:
        self.fragments = fragments or []
        self.documents: dict[str, tuple[str, list]] = {}

    def rechercher(self, embedding: list[float], limite: int) -> list[FragmentTrouve]:
        return self.fragments[:limite]

    def remplacer_document(self, source, titre, fragments) -> None:
        self.documents[source] = (titre, fragments)
