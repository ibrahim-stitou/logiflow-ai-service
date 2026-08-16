"""Agent copilote conversationnel : répond en langage naturel aux questions de l'exploitant.

MVP : appelle directement le LLM (Ollama) avec la question, sans recherche documentaire (RAG). Les
`sources` renvoyées sont donc toujours vides pour l'instant — à enrichir en branchant une base
vectorielle (véhicules, voyages, dossiers) une fois le besoin métier priorisé. `confiance` est une
valeur fixe faute de signal fiable venant du LLM ; à remplacer par une vraie métrique si un jour
disponible (score de recherche RAG, log-probs, etc.).
"""

from logiflow_ai_service.agents.copilot.schemas import CopilotAskRequest, CopilotAskResponse
from logiflow_ai_service.infrastructure.ollama_client import OllamaClient

_SYSTEM_PROMPT = (
    "Tu es le copilote de LogiFlow, un TMS (Transport Management System) pour le transport "
    "routier de marchandises. Réponds de façon concise et factuelle aux questions des "
    "exploitants sur les véhicules, chauffeurs, voyages et dossiers de transport. Si tu ne "
    "disposes pas d'une information, dis-le clairement plutôt que d'inventer une réponse."
)

_CONFIANCE_PAR_DEFAUT = 0.5


class CopiloteService:
    def __init__(self, ollama_client: OllamaClient) -> None:
        self._ollama_client = ollama_client

    def repondre(self, request: CopilotAskRequest) -> CopilotAskResponse:
        contenu = self._ollama_client.chat(_SYSTEM_PROMPT, request.question)
        return CopilotAskResponse(
            reponse=contenu,
            sources=[],
            confiance=_CONFIANCE_PAR_DEFAUT,
        )
