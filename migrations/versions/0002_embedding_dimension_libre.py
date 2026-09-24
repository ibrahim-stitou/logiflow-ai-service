"""Embeddings de dimension libre (fournisseur d'embeddings configurable).

Le fournisseur LLM n'est plus Ollama : chaque modèle d'embeddings a sa propre dimension
(768, 1024, 1536…). La colonne devient `vector` sans dimension ; l'index HNSW, qui en exige
une, est retiré (recherche exacte, suffisante pour quelques centaines de fragments). Les
fragments existants, calculés avec l'ancien modèle, sont incompatibles : ils sont supprimés
(réingérer avec `make ingerer`).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCHEMA = "copilote"


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_fragment_connaissance_embedding")
    op.execute(f"TRUNCATE {SCHEMA}.document_connaissance CASCADE")
    op.execute(f"ALTER TABLE {SCHEMA}.fragment_connaissance ALTER COLUMN embedding TYPE vector")


def downgrade() -> None:
    op.execute(f"TRUNCATE {SCHEMA}.document_connaissance CASCADE")
    op.execute(
        f"ALTER TABLE {SCHEMA}.fragment_connaissance ALTER COLUMN embedding TYPE vector(768)"
    )
    op.execute(
        f"CREATE INDEX ix_fragment_connaissance_embedding ON {SCHEMA}.fragment_connaissance "
        "USING hnsw (embedding vector_cosine_ops)"
    )
