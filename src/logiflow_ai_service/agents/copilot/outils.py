"""Boîte à outils du copilote : outils métier exécutés par Spring + outils locaux au service IA.

Contrat d'un résultat d'outil (côté Spring comme local) :
    {"resultats": [...], "total": int, "sources": [{"type", "reference", "id"}]}
Les `sources` alimentent les liens cliquables de la réponse ; le reste est renvoyé tel quel au LLM.
"""

import logging
from dataclasses import dataclass
from typing import Any

from logiflow_ai_service.agents.copilot.model import ConnaissanceRepository
from logiflow_ai_service.infrastructure.backend_client import BackendClient
from logiflow_ai_service.infrastructure.llm_client import LlmClient

logger = logging.getLogger(__name__)

OUTIL_CONNAISSANCE = "rechercher_base_connaissance"

_DEFINITION_CONNAISSANCE = {
    "nom": OUTIL_CONNAISSANCE,
    "libelle": "Consultation de la documentation",
    "description": (
        "Recherche dans la documentation fonctionnelle de LogiFlow (procédures, fonctionnement "
        "des écrans, règles métier). À utiliser pour les questions « comment faire… » sur "
        "l'application."
    ),
    "parametres": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "La question reformulée"},
        },
        "required": ["question"],
    },
}


@dataclass(frozen=True)
class ContexteAppel:
    """Identité de l'appelant, fournie par Spring pour CE message."""

    jeton: str
    utilisateur_id: str
    nom: str
    roles: list[str]
    correlation_id: str | None = None


class BoiteOutils:
    def __init__(
        self,
        backend: BackendClient,
        llm: LlmClient,
        connaissance: ConnaissanceRepository | None,
    ) -> None:
        self._backend = backend
        self._llm = llm
        self._connaissance = connaissance

    def catalogue(self, contexte: ContexteAppel) -> list[dict[str, Any]]:
        """Outils disponibles pour cet utilisateur (Spring filtre selon ses rôles)."""
        catalogue = list(
            self._backend.catalogue_outils(contexte.jeton, contexte.roles, contexte.correlation_id)
        )
        if self._connaissance is not None:
            catalogue.append(_DEFINITION_CONNAISSANCE)
        return catalogue

    def executer(self, nom: str, arguments: dict[str, Any], contexte: ContexteAppel) -> dict:
        if nom == OUTIL_CONNAISSANCE and self._connaissance is not None:
            return self._rechercher_connaissance(str(arguments.get("question", "")))
        return self._backend.executer_outil(nom, arguments, contexte.jeton, contexte.correlation_id)

    def _rechercher_connaissance(self, question: str) -> dict[str, Any]:
        if not question.strip():
            return {"resultats": [], "total": 0, "sources": []}
        [embedding] = self._llm.embed([question])
        fragments = self._connaissance.rechercher(embedding, limite=5)
        return {
            "resultats": [
                {"document": f.titre, "extrait": f.contenu, "pertinence": round(f.score, 3)}
                for f in fragments
            ],
            "total": len(fragments),
            "sources": [],
        }


def en_outils_llm(catalogue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format `tools` de l'API /chat/completions (compatible OpenAI)."""
    return [
        {
            "type": "function",
            "function": {
                "name": outil["nom"],
                "description": outil["description"],
                "parameters": outil["parametres"],
            },
        }
        for outil in catalogue
    ]
