"""Base de connaissance vectorielle (pgvector) : recherche par similarité cosinus."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from logiflow_ai_service.agents.copilot.model import FragmentTrouve
from logiflow_ai_service.infrastructure.persistence.models import (
    DocumentConnaissanceModel,
    FragmentConnaissanceModel,
)


class SqlConnaissanceRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def rechercher(self, embedding: list[float], limite: int) -> list[FragmentTrouve]:
        distance = FragmentConnaissanceModel.embedding.cosine_distance(embedding)
        with self._session_factory() as session:
            lignes = session.execute(
                select(
                    DocumentConnaissanceModel.source,
                    DocumentConnaissanceModel.titre,
                    FragmentConnaissanceModel.contenu,
                    distance.label("distance"),
                )
                .join(
                    DocumentConnaissanceModel,
                    DocumentConnaissanceModel.id == FragmentConnaissanceModel.document_id,
                )
                .order_by(distance)
                .limit(limite)
            )
            return [
                FragmentTrouve(
                    source=ligne.source,
                    titre=ligne.titre,
                    contenu=ligne.contenu,
                    score=1 - ligne.distance,
                )
                for ligne in lignes
            ]

    def remplacer_document(
        self, source: str, titre: str, fragments: list[tuple[str, list[float]]]
    ) -> None:
        """Réingestion idempotente : l'ancienne version du document est supprimée en cascade."""
        with self._session_factory.begin() as session:
            session.execute(
                delete(DocumentConnaissanceModel).where(DocumentConnaissanceModel.source == source)
            )
            document_id = uuid.uuid4()
            session.add(DocumentConnaissanceModel(id=document_id, source=source, titre=titre))
            session.flush()
            session.add_all(
                FragmentConnaissanceModel(
                    id=uuid.uuid4(),
                    document_id=document_id,
                    ordre=ordre,
                    contenu=contenu,
                    embedding=embedding,
                )
                for ordre, (contenu, embedding) in enumerate(fragments)
            )
