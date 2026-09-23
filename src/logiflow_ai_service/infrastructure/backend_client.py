"""Client HTTP vers les OUTILS du copilote exposés par Spring Boot (`/internal/copilote/**`).

Le service IA n'accède jamais à la base TMS : pour obtenir une donnée métier, le LLM choisit un
outil et ce client demande à Spring de l'exécuter. Chaque appel porte :
- `X-Internal-Api-Key` : le secret de rappel (distinct de celui que Spring nous présente) ;
- `X-Copilote-Contexte` : le jeton opaque reçu de Spring pour CE message. Spring y retrouve
  l'utilisateur et ses rôles, et filtre les outils et les données en conséquence — le service IA
  ne peut donc jamais obtenir plus que ce que l'utilisateur a le droit de voir.
"""

import logging
import time
from typing import Any

import httpx

from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError

logger = logging.getLogger(__name__)

HEADER_CLE = "X-Internal-Api-Key"
HEADER_CONTEXTE = "X-Copilote-Contexte"
HEADER_CORRELATION = "X-Correlation-Id"

_TTL_CATALOGUE_S = 300.0


class ErreurOutil(Exception):
    """L'outil a refusé la requête (arguments invalides, droits) : message renvoyé au LLM."""

    def __init__(self, statut: int, message: str) -> None:
        self.statut = statut
        super().__init__(message)


class BackendClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s
        # Catalogue mis en cache par jeu de rôles (il ne dépend que des rôles de l'utilisateur).
        self._cache_catalogue: dict[frozenset[str], tuple[float, list[dict[str, Any]]]] = {}

    def _headers(self, contexte: str, correlation_id: str | None) -> dict[str, str]:
        headers = {HEADER_CLE: self._api_key, HEADER_CONTEXTE: contexte}
        if correlation_id:
            headers[HEADER_CORRELATION] = correlation_id
        return headers

    def catalogue_outils(
        self, contexte: str, roles: list[str], correlation_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Outils autorisés pour l'utilisateur : [{nom, libelle, description, parametres}]."""
        cle = frozenset(roles)
        en_cache = self._cache_catalogue.get(cle)
        if en_cache and time.monotonic() - en_cache[0] < _TTL_CATALOGUE_S:
            return en_cache[1]
        try:
            response = httpx.get(
                f"{self._base_url}/internal/copilote/outils",
                headers=self._headers(contexte, correlation_id),
                timeout=self._timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Catalogue d'outils indisponible : %s", exc)
            raise UpstreamServiceError("backend", str(exc)) from exc
        catalogue = response.json()
        self._cache_catalogue[cle] = (time.monotonic(), catalogue)
        return catalogue

    def executer_outil(
        self,
        nom: str,
        arguments: dict[str, Any],
        contexte: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Exécute un outil côté Spring.

        :raises ErreurOutil: refus fonctionnel (4xx) — à renvoyer au LLM pour qu'il se corrige.
        :raises UpstreamServiceError: Spring injoignable ou en erreur (5xx).
        """
        try:
            response = httpx.post(
                f"{self._base_url}/internal/copilote/outils/{nom}",
                json=arguments,
                headers=self._headers(contexte, correlation_id),
                timeout=self._timeout_s,
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError("backend", str(exc)) from exc
        if 400 <= response.status_code < 500:
            raise ErreurOutil(response.status_code, _detail(response))
        if response.is_error:
            raise UpstreamServiceError("backend", f"HTTP {response.status_code}")
        return response.json()


def _detail(response: httpx.Response) -> str:
    try:
        corps = response.json()
    except ValueError:
        return response.text[:300] or f"HTTP {response.status_code}"
    return str(corps.get("detail") or corps.get("title") or corps)[:500]
