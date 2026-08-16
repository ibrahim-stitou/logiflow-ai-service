"""Schémas du contrat POST /internal/ai/v1/groupage/analyser (voir docs/integration-ia.md)."""

from pydantic import Field

from logiflow_ai_service.schemas import CamelModel


class DossierCandidat(CamelModel):
    id: str
    reference: str
    poids_brut_kg: float
    volume_m3: float
    nb_palettes: int
    contient_adr: bool


class GroupageAnalyserRequest(CamelModel):
    dossiers: list[DossierCandidat]
    correlation_id: str | None = None


class PropositionGroupage(CamelModel):
    dossier_ids: list[str]
    score: float
    confiance: float
    gain_km: float | None = None
    gain_marge: float | None = None
    justification: str


class GroupageAnalyserResponse(CamelModel):
    propositions: list[PropositionGroupage] = Field(default_factory=list)
