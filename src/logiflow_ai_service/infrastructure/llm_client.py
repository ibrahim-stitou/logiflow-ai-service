"""Client LLM « compatible OpenAI » (API /chat/completions), utilisé par l'agent copilote.

Un seul client pour tous les fournisseurs exposant ce format : Groq, Google Gemini, Mistral,
OpenRouter, OpenAI… (voir .env.example). Le fournisseur se choisit par configuration
(`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) ; rien d'autre ne dépend de lui.

- `chat()` : un tour, non streamé (ancienne route /copilot/ask, génération de titres) ;
- `chat_stream()` : conversation multi-tours avec outils (tool-calling), streamée en SSE ;
- `embed()` : embeddings pour la base de connaissance (fournisseur éventuellement distinct) ;
- `etat()` : disponibilité du fournisseur, de la clé et du modèle (sonde /health).
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from logiflow_ai_service.infrastructure.exceptions import LlmQuotaError, UpstreamServiceError

logger = logging.getLogger(__name__)

_SERVICE = "llm"


@dataclass(frozen=True)
class AppelOutilLlm:
    """Appel d'outil demandé par le LLM (identifiant à rappeler dans le message `tool`)."""

    id: str
    nom: str
    arguments: dict[str, Any]


@dataclass
class FragmentChat:
    """Un fragment du flux : texte partiel, ou bilan final (`fini`) avec les appels d'outils."""

    contenu: str = ""
    appels_outils: list[AppelOutilLlm] = field(default_factory=list)
    fini: bool = False
    tokens_prompt: int | None = None
    tokens_completion: int | None = None


class LlmClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float,
        *,
        stream_timeout_s: float = 120.0,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        embed_base_url: str | None = None,
        embed_api_key: str | None = None,
        embed_model: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._stream_timeout_s = stream_timeout_s
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._embed_base_url = (embed_base_url or base_url).rstrip("/")
        self._embed_api_key = embed_api_key or api_key
        self._embed_model = embed_model or None

    @property
    def model(self) -> str:
        return self._model

    @property
    def embeddings_disponibles(self) -> bool:
        return self._embed_model is not None

    def _headers(self, api_key: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key or self._api_key}"}

    def _corps(self, messages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            **extra,
        }

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Conversation à un tour, non streamée.

        :raises UpstreamServiceError: fournisseur injoignable, clé refusée ou réponse invalide.
        """
        corps = self._corps(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=corps,
                headers=self._headers(),
                timeout=self._timeout_s,
            )
        except httpx.HTTPError as exc:
            logger.warning("Appel LLM échoué : %s", exc)
            raise UpstreamServiceError(_SERVICE, str(exc)) from exc
        _verifier(response)
        try:
            contenu = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise UpstreamServiceError(_SERVICE, "Réponse mal formée") from exc
        if not contenu:
            raise UpstreamServiceError(_SERVICE, "Réponse vide")
        return contenu

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        forcer_reponse: bool = False,
    ) -> Iterator[FragmentChat]:
        """Conversation multi-tours streamée.

        Les fragments de texte sont émis au fil de l'eau ; les appels d'outils (dont les arguments
        arrivent morceau par morceau) sont réassemblés et rendus dans le fragment final `fini`.
        `forcer_reponse` interdit tout nouvel appel d'outil (`tool_choice: none`) tout en
        conservant la définition des outils, exigée par certains fournisseurs quand l'historique
        contient déjà des appels.

        :raises LlmQuotaError: quota du palier gratuit atteint (HTTP 429).
        :raises UpstreamServiceError: fournisseur injoignable, clé refusée ou flux invalide.
        """
        extra: dict[str, Any] = {"stream": True}
        if tools:
            extra["tools"] = tools
            extra["tool_choice"] = "none" if forcer_reponse else "auto"
        corps = self._corps(messages, **extra)
        appels: dict[int, dict[str, str]] = {}
        usage: dict[str, Any] = {}
        timeout = httpx.Timeout(self._stream_timeout_s, connect=10.0)
        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=corps,
                headers=self._headers(),
                timeout=timeout,
            ) as response:
                if response.is_error:
                    response.read()
                    _verifier(response)
                for ligne in response.iter_lines():
                    if not ligne.startswith("data:"):
                        continue
                    donnees = ligne[len("data:") :].strip()
                    if donnees == "[DONE]":
                        break
                    morceau = json.loads(donnees)
                    if "error" in morceau:
                        raise UpstreamServiceError(_SERVICE, str(morceau["error"])[:300])
                    # Groq renvoie l'usage dans x_groq.usage, OpenAI dans usage.
                    usage = (
                        morceau.get("usage") or (morceau.get("x_groq") or {}).get("usage") or usage
                    )
                    for choix in morceau.get("choices") or []:
                        delta = choix.get("delta") or {}
                        if delta.get("content"):
                            yield FragmentChat(contenu=delta["content"])
                        for appel in delta.get("tool_calls") or []:
                            _accumuler(appels, appel)
        except httpx.HTTPError as exc:
            logger.warning("Flux LLM échoué : %s", exc)
            raise UpstreamServiceError(_SERVICE, str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise UpstreamServiceError(_SERVICE, "Flux mal formé") from exc

        yield FragmentChat(
            appels_outils=[_appel(appels[i]) for i in sorted(appels)],
            fini=True,
            tokens_prompt=usage.get("prompt_tokens"),
            tokens_completion=usage.get("completion_tokens"),
        )

    def embed(self, textes: list[str]) -> list[list[float]]:
        """Embeddings (base de connaissance).

        :raises UpstreamServiceError: aucun modèle d'embeddings configuré, ou échec du fournisseur.
        """
        if self._embed_model is None:
            raise UpstreamServiceError(_SERVICE, "Aucun modèle d'embeddings configuré")
        try:
            response = httpx.post(
                f"{self._embed_base_url}/embeddings",
                json={"model": self._embed_model, "input": textes},
                headers=self._headers(self._embed_api_key),
                timeout=self._stream_timeout_s,
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(_SERVICE, str(exc)) from exc
        _verifier(response)
        donnees = sorted(response.json().get("data") or [], key=lambda d: d.get("index", 0))
        embeddings = [d.get("embedding") for d in donnees]
        if len(embeddings) != len(textes) or not all(embeddings):
            raise UpstreamServiceError(_SERVICE, "Embeddings absents ou incomplets")
        return embeddings

    def etat(self) -> str:
        """UP, CLE_ABSENTE, CLE_INVALIDE, MODELE_ABSENT ou DOWN — via GET /models (gratuit)."""
        if not self._api_key:
            return "CLE_ABSENTE"
        try:
            response = httpx.get(f"{self._base_url}/models", headers=self._headers(), timeout=5.0)
        except httpx.HTTPError:
            return "DOWN"
        if response.status_code in (401, 403):
            return "CLE_INVALIDE"
        if not response.is_success:
            return "DOWN"
        try:
            ids = {m.get("id") for m in response.json().get("data") or []}
        except ValueError:
            return "DOWN"
        # Certains fournisseurs préfixent (ex. Gemini : "models/gemini-…").
        disponible = any(i == self._model or (i or "").endswith("/" + self._model) for i in ids)
        return "UP" if disponible or not ids else "MODELE_ABSENT"


def _verifier(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise LlmQuotaError(_SERVICE, _message_erreur(response))
    if response.is_error:
        raise UpstreamServiceError(
            _SERVICE, f"HTTP {response.status_code} : {_message_erreur(response)}"
        )


def _message_erreur(response: httpx.Response) -> str:
    try:
        corps = response.json()
    except ValueError:
        return response.text[:300]
    erreur = corps.get("error") if isinstance(corps, dict) else None
    if isinstance(erreur, dict):
        return str(erreur.get("message") or erreur)[:300]
    return str(erreur or corps)[:300]


def _accumuler(appels: dict[int, dict[str, str]], delta: dict[str, Any]) -> None:
    index = delta.get("index", 0)
    appel = appels.setdefault(index, {"id": "", "nom": "", "arguments": ""})
    if delta.get("id"):
        appel["id"] = delta["id"]
    fonction = delta.get("function") or {}
    if fonction.get("name"):
        appel["nom"] = fonction["name"]
    arguments = fonction.get("arguments")
    if isinstance(arguments, dict):  # certains fournisseurs envoient l'objet d'un coup
        appel["arguments"] = json.dumps(arguments)
    elif arguments:
        appel["arguments"] += arguments


def _appel(brut: dict[str, str]) -> AppelOutilLlm:
    try:
        arguments = json.loads(brut["arguments"]) if brut["arguments"].strip() else {}
    except json.JSONDecodeError:
        arguments = {}
    return AppelOutilLlm(
        id=brut["id"] or f"appel-{brut['nom']}",
        nom=brut["nom"],
        arguments=arguments if isinstance(arguments, dict) else {},
    )
