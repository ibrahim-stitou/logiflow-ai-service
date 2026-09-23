"""Client HTTP vers un serveur Ollama auto-hébergé (LLM), utilisé par l'agent copilote.

Deux modes :
- `chat()` : un tour, non streamé (ancienne route /copilot/ask, génération de titres) ;
- `chat_stream()` : conversation multi-tours avec outils (tool-calling), streamée fragment par
  fragment (NDJSON d'Ollama) pour être relayée en SSE jusqu'à Angular via Spring Boot.
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError

logger = logging.getLogger(__name__)


@dataclass
class FragmentChat:
    """Un fragment du flux Ollama : texte partiel, appels d'outils, ou bilan final (`fini`)."""

    contenu: str = ""
    appels_outils: list[dict[str, Any]] = field(default_factory=list)
    fini: bool = False
    tokens_prompt: int | None = None
    tokens_completion: int | None = None


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        *,
        stream_timeout_s: float = 120.0,
        embed_model: str = "nomic-embed-text",
        num_ctx: int = 8192,
        temperature: float = 0.2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._stream_timeout_s = stream_timeout_s
        self._embed_model = embed_model
        self._options = {"num_ctx": num_ctx, "temperature": temperature}

    @property
    def model(self) -> str:
        return self._model

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
            "options": self._options,
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

    def chat_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> Iterator[FragmentChat]:
        """Conversation multi-tours streamée. Les appels d'outils arrivent dans un fragment.

        :raises UpstreamServiceError: si Ollama est injoignable, répond en erreur ou coupe le flux.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": self._options,
        }
        if tools:
            payload["tools"] = tools
        timeout = httpx.Timeout(self._stream_timeout_s, connect=5.0)
        try:
            with httpx.stream(
                "POST", f"{self._base_url}/api/chat", json=payload, timeout=timeout
            ) as response:
                if response.is_error:
                    response.read()
                    raise UpstreamServiceError(
                        "ollama", f"HTTP {response.status_code} : {response.text[:300]}"
                    )
                for ligne in response.iter_lines():
                    if not ligne.strip():
                        continue
                    yield self._fragment(json.loads(ligne))
        except httpx.HTTPError as exc:
            logger.warning("Flux Ollama échoué : %s", exc)
            raise UpstreamServiceError("ollama", str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise UpstreamServiceError("ollama", "Flux mal formé") from exc

    @staticmethod
    def _fragment(corps: dict[str, Any]) -> FragmentChat:
        if "error" in corps:
            raise UpstreamServiceError("ollama", str(corps["error"]))
        message = corps.get("message") or {}
        return FragmentChat(
            contenu=message.get("content") or "",
            appels_outils=message.get("tool_calls") or [],
            fini=bool(corps.get("done")),
            tokens_prompt=corps.get("prompt_eval_count"),
            tokens_completion=corps.get("eval_count"),
        )

    def embed(self, textes: list[str]) -> list[list[float]]:
        """Embeddings (base de connaissance). :raises UpstreamServiceError: si Ollama échoue."""
        try:
            response = httpx.post(
                f"{self._base_url}/api/embed",
                json={"model": self._embed_model, "input": textes},
                timeout=self._stream_timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamServiceError("ollama", str(exc)) from exc
        embeddings = response.json().get("embeddings")
        if not embeddings or len(embeddings) != len(textes):
            raise UpstreamServiceError("ollama", "Embeddings absents ou incomplets")
        return embeddings

    def est_disponible(self) -> bool:
        try:
            return httpx.get(f"{self._base_url}/api/tags", timeout=2.0).is_success
        except httpx.HTTPError:
            return False
