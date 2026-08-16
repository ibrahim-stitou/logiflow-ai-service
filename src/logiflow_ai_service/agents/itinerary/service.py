"""Agent itinéraire : calcule le meilleur trajet routier passant par une liste de points.

Délègue entièrement à OSRM (routing réel sur le réseau routier) : contrairement au groupage, il
n'existe pas de repli déterministe pertinent en cas d'indisponibilité — estimer une distance
routière sans moteur de routing reviendrait à afficher un chiffre trompeur. Voir
`AiServiceHttpAdapter` côté backend : cet agent propage l'échec en 503 comme le copilote.
"""

from logiflow_ai_service.agents.itinerary.schemas import (
    ItineraryCalculerRequest,
    ItineraryCalculerResponse,
    SegmentItineraire,
)
from logiflow_ai_service.infrastructure.osrm_client import OsrmClient


class ItineraryService:
    def __init__(self, osrm_client: OsrmClient) -> None:
        self._osrm_client = osrm_client

    def calculer(self, request: ItineraryCalculerRequest) -> ItineraryCalculerResponse:
        coords = [(p.latitude, p.longitude) for p in request.points]
        route = self._osrm_client.calculer_itineraire(coords)

        segments = [
            SegmentItineraire(
                depart=request.points[i],
                arrivee=request.points[i + 1],
                distance_km=round(leg.distance_km, 1),
                duree_min=round(leg.duree_min, 1),
            )
            for i, leg in enumerate(route.legs)
        ]

        return ItineraryCalculerResponse(
            distance_km=round(route.distance_km, 1),
            duree_min=round(route.duree_min, 1),
            segments=segments,
        )
