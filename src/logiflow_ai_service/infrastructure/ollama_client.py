"""Client HTTP vers un serveur Ollama auto-hébergé (LLM), utilisé par l'agent copilote.

Ollama est appelé en mode non-streaming (`stream: false`) via son API `/api/chat` : plus simple à
intégrer côté Flask synchrone, au prix de la latence complète de génération avant réponse — à
revoir si le copilote doit un jour streamer sa réponse jusqu'à Angular via Spring Boot.
"""

import logging

import httpx

from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Envoie une conversation à un tour à Ollama et renvoie le contenu de la réponse.

        :raises UpstreamServiceError: si Ollama est injoignable ou répond en erreur.
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Appel Ollama échoué : %s", exc)
            raise UpstreamServiceError("ollama", str(exc)) from exc

        body = response.json()
        message = body.get("message", {})
        content = message.get("content")
        if not content:
            raise UpstreamServiceError("ollama", "Réponse vide ou mal formée")
        return content
