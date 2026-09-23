"""Implémentation SQL (SQLAlchemy 2) du `ConversationRepository` du copilote.

Chaque méthode ouvre sa propre session courte : le flux SSE d'une réponse peut durer plusieurs
dizaines de secondes, il ne doit pas garder une transaction (ni une connexion) ouverte pendant ce
temps.
"""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from logiflow_ai_service.agents.copilot.model import (
    AppelOutil,
    Conversation,
    Message,
    Role,
    Source,
    StatutMessage,
    maintenant,
)
from logiflow_ai_service.infrastructure.persistence.models import (
    AppelOutilModel,
    ConversationModel,
    FeedbackModel,
    MessageModel,
)


def _conversation(model: ConversationModel) -> Conversation:
    return Conversation(
        id=model.id,
        utilisateur_id=model.utilisateur_id,
        titre=model.titre,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _message(model: MessageModel) -> Message:
    return Message(
        id=model.id,
        conversation_id=model.conversation_id,
        role=Role(model.role),
        contenu=model.contenu,
        statut=StatutMessage(model.statut),
        sources=[Source(**s) for s in model.sources or []],
        modele=model.modele,
        tokens_prompt=model.tokens_prompt,
        tokens_completion=model.tokens_completion,
        duree_ms=model.duree_ms,
        created_at=model.created_at,
    )


class SqlConversationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def creer(self, conversation: Conversation) -> Conversation:
        with self._session_factory.begin() as session:
            session.add(
                ConversationModel(
                    id=conversation.id,
                    utilisateur_id=conversation.utilisateur_id,
                    titre=conversation.titre,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
            )
        return conversation

    def lister(self, utilisateur_id: str, limite: int, decalage: int) -> list[Conversation]:
        with self._session_factory() as session:
            modeles = session.scalars(
                select(ConversationModel)
                .where(ConversationModel.utilisateur_id == utilisateur_id)
                .order_by(ConversationModel.updated_at.desc())
                .limit(limite)
                .offset(decalage)
            )
            return [_conversation(m) for m in modeles]

    def obtenir(self, conversation_id: UUID, utilisateur_id: str) -> Conversation | None:
        with self._session_factory() as session:
            model = session.get(ConversationModel, conversation_id)
            if model is None or model.utilisateur_id != utilisateur_id:
                return None
            return _conversation(model)

    def renommer(
        self, conversation_id: UUID, utilisateur_id: str, titre: str
    ) -> Conversation | None:
        with self._session_factory.begin() as session:
            model = session.get(ConversationModel, conversation_id)
            if model is None or model.utilisateur_id != utilisateur_id:
                return None
            model.titre = titre
            model.updated_at = maintenant()
            return _conversation(model)

    def supprimer(self, conversation_id: UUID, utilisateur_id: str) -> bool:
        with self._session_factory.begin() as session:
            resultat = session.execute(
                delete(ConversationModel).where(
                    ConversationModel.id == conversation_id,
                    ConversationModel.utilisateur_id == utilisateur_id,
                )
            )
            return resultat.rowcount > 0

    def enregistrer_message(self, message: Message) -> Message:
        with self._session_factory.begin() as session:
            session.merge(
                MessageModel(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    role=message.role.value,
                    contenu=message.contenu,
                    statut=message.statut.value,
                    sources=[s.en_dict() for s in message.sources],
                    modele=message.modele,
                    tokens_prompt=message.tokens_prompt,
                    tokens_completion=message.tokens_completion,
                    duree_ms=message.duree_ms,
                    created_at=message.created_at,
                )
            )
            session.execute(
                update(ConversationModel)
                .where(ConversationModel.id == message.conversation_id)
                .values(updated_at=maintenant())
            )
        return message

    def messages(self, conversation_id: UUID, limite: int | None = None) -> list[Message]:
        with self._session_factory() as session:
            requete = (
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.created_at.desc())
            )
            if limite is not None:
                requete = requete.limit(limite)
            return [_message(m) for m in reversed(list(session.scalars(requete)))]

    def enregistrer_appel_outil(self, appel: AppelOutil) -> None:
        with self._session_factory.begin() as session:
            session.add(
                AppelOutilModel(
                    id=appel.id,
                    message_id=appel.message_id,
                    nom=appel.nom,
                    arguments=appel.arguments,
                    succes=appel.succes,
                    duree_ms=appel.duree_ms,
                    nb_resultats=appel.nb_resultats,
                    erreur=appel.erreur,
                )
            )

    def enregistrer_feedback(
        self, message_id: UUID, utilisateur_id: str, note: int, commentaire: str | None
    ) -> bool:
        with self._session_factory.begin() as session:
            proprietaire = session.scalar(
                select(ConversationModel.utilisateur_id)
                .join(MessageModel, MessageModel.conversation_id == ConversationModel.id)
                .where(MessageModel.id == message_id)
            )
            if proprietaire != utilisateur_id:
                return False
            session.merge(
                FeedbackModel(
                    message_id=message_id,
                    utilisateur_id=utilisateur_id,
                    note=note,
                    commentaire=commentaire,
                )
            )
            return True
