"""Schéma initial du copilote : conversations, messages, outils, feedback, base de connaissance.

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "copilote"


def upgrade() -> None:
    # Requiert un superutilisateur si absente : normalement créée par 02-ai-database.sql.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "conversation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("utilisateur_id", sa.String(255), nullable=False),
        sa.Column("titre", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_conversation_utilisateur_maj",
        "conversation",
        ["utilisateur_id", "updated_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "message",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("contenu", sa.Text, nullable=False),
        sa.Column("statut", sa.String(20), nullable=False),
        sa.Column("sources", JSONB, nullable=False, server_default="[]"),
        sa.Column("modele", sa.String(100)),
        sa.Column("tokens_prompt", sa.Integer),
        sa.Column("tokens_completion", sa.Integer),
        sa.Column("duree_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_message_conversation_date",
        "message",
        ["conversation_id", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "appel_outil",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.message.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nom", sa.String(100), nullable=False),
        sa.Column("arguments", JSONB, nullable=False),
        sa.Column("succes", sa.Boolean, nullable=False),
        sa.Column("duree_ms", sa.Integer, nullable=False),
        sa.Column("nb_resultats", sa.Integer),
        sa.Column("erreur", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_appel_outil_message_id", "appel_outil", ["message_id"], schema=SCHEMA)

    op.create_table(
        "feedback",
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.message.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("utilisateur_id", sa.String(255), nullable=False),
        sa.Column("note", sa.SmallInteger, nullable=False),
        sa.Column("commentaire", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("note IN (-1, 1)", name="ck_feedback_note"),
        schema=SCHEMA,
    )

    op.create_table(
        "document_connaissance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(500), nullable=False, unique=True),
        sa.Column("titre", sa.String(300), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "fragment_connaissance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.document_connaissance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordre", sa.Integer, nullable=False),
        sa.Column("contenu", sa.Text, nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fragment_connaissance_document_id",
        "fragment_connaissance",
        ["document_id"],
        schema=SCHEMA,
    )
    op.execute(
        f"CREATE INDEX ix_fragment_connaissance_embedding ON {SCHEMA}.fragment_connaissance "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    for table in (
        "fragment_connaissance",
        "document_connaissance",
        "feedback",
        "appel_outil",
        "message",
        "conversation",
    ):
        op.drop_table(table, schema=SCHEMA)
