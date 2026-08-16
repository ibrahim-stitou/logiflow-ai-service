"""Schémas du contrat POST /internal/ai/v1/copilot/ask (voir docs/integration-ia.md)."""

from pydantic import Field

from logiflow_ai_service.schemas import CamelModel


class Utilisateur(CamelModel):
    id: str
    roles: list[str] = Field(default_factory=list)


class CopilotAskRequest(CamelModel):
    question: str
    utilisateur: Utilisateur
    correlation_id: str | None = None


class CopilotAskResponse(CamelModel):
    reponse: str
    sources: list[str] = Field(default_factory=list)
    confiance: float | None = None
