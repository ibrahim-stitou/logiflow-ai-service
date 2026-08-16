"""Schémas du contrat POST /internal/ai/v1/itinerary/calculer.

Nouveau contrat (voir docs/integration-ia.md côté backend, section "Agent itinéraire") : calcule
le meilleur trajet routier passant par une liste de points ordonnée. Les coordonnées reprennent le
format du VO partagé `com.logiflow.tms.shared.domain.vo.GeoPoint` côté Spring Boot
(latitude/longitude WGS84).
"""

from pydantic import Field, field_validator

from logiflow_ai_service.schemas import CamelModel


class PointGeo(CamelModel):
    latitude: float
    longitude: float
    libelle: str | None = None


class ItineraryCalculerRequest(CamelModel):
    points: list[PointGeo]
    correlation_id: str | None = None

    @field_validator("points")
    @classmethod
    def _au_moins_deux_points(cls, points: list[PointGeo]) -> list[PointGeo]:
        if len(points) < 2:
            raise ValueError("Au moins deux points sont requis pour calculer un itinéraire")
        return points


class SegmentItineraire(CamelModel):
    depart: PointGeo
    arrivee: PointGeo
    distance_km: float
    duree_min: float


class ItineraryCalculerResponse(CamelModel):
    distance_km: float
    duree_min: float
    segments: list[SegmentItineraire] = Field(default_factory=list)
