"""Exceptions communes aux clients d'infrastructure (Ollama, OSRM, ...).

Chaque client d'infrastructure traduit ses erreurs réseau/HTTP en `UpstreamServiceError` : les
routes n'ont besoin de connaître qu'un seul type d'échec pour répondre 502/503 de façon uniforme,
quel que soit le service tiers en cause.
"""


class UpstreamServiceError(RuntimeError):
    """Le service tiers (Ollama, OSRM, ...) est indisponible ou a répondu en erreur."""

    def __init__(self, service: str, message: str) -> None:
        self.service = service
        super().__init__(f"[{service}] {message}")
