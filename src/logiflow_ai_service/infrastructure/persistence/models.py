"""Modèle relationnel de la base `logiflow_ai`, schéma `copilote` (migrations Alembic)."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "copilote"
DIMENSION_EMBEDDING = 768  # nomic-embed-text


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class ConversationModel(Base):
    __tablename__ = "conversation"
    __table_args__ = (Index("ix_conversation_utilisateur_maj", "utilisateur_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    utilisateur_id: Mapped[str] = mapped_column(String(255), nullable=False)
    titre: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MessageModel(Base):
    __tablename__ = "message"
    __table_args__ = (Index("ix_message_conversation_date", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    contenu: Mapped[str] = mapped_column(Text, nullable=False)
    statut: Mapped[str] = mapped_column(String(20), nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    modele: Mapped[str | None] = mapped_column(String(100))
    tokens_prompt: Mapped[int | None] = mapped_column(Integer)
    tokens_completion: Mapped[int | None] = mapped_column(Integer)
    duree_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AppelOutilModel(Base):
    __tablename__ = "appel_outil"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    succes: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duree_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    nb_resultats: Mapped[int | None] = mapped_column(Integer)
    erreur: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FeedbackModel(Base):
    __tablename__ = "feedback"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("message.id", ondelete="CASCADE"), primary_key=True
    )
    utilisateur_id: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    commentaire: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DocumentConnaissanceModel(Base):
    __tablename__ = "document_connaissance"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    titre: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FragmentConnaissanceModel(Base):
    __tablename__ = "fragment_connaissance"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_connaissance.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordre: Mapped[int] = mapped_column(Integer, nullable=False)
    contenu: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSION_EMBEDDING), nullable=False)
