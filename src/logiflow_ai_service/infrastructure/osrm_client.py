"""Client HTTP vers un serveur OSRM (Open Source Routing Machine), utilisé par l'agent itinéraire.

Pointe par défaut sur la démo publique `router.project-osrm.org` (gratuite, sans clé API) ; à
remplacer par une instance auto-hébergée en production, sans dépendance payante — voir
docs/architecture.md.
"""

import logging
from dataclasses import dataclass

import httpx

from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteLeg:
    distance_km: float
    duree_min: float


@dataclass(frozen=True)
class Route:
    distance_km: float
    duree_min: float
    legs: list[RouteLeg]


class OsrmClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def calculer_itineraire(self, points: list[tuple[float, float]]) -> Route:
        """Calcule un itinéraire routier passant par les points donnés, dans l'ordre.

        :param points: liste de (latitude, longitude), au moins 2 points.
        :raises UpstreamServiceError: si OSRM est injoignable, répond en erreur, ou ne trouve
            aucun itinéraire viable entre les points fournis.
        """
        # OSRM attend "longitude,latitude" (ordre inverse du couple usuel latitude/longitude).
        coords = ";".join(f"{lon},{lat}" for lat, lon in points)
        url = f"{self._base_url}/route/v1/driving/{coords}"

        try:
            response = httpx.get(
                url,
                params={"overview": "false", "alternatives": "false", "steps": "false"},
                timeout=self._timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Appel OSRM échoué : %s", exc)
            raise UpstreamServiceError("osrm", str(exc)) from exc

        body = response.json()
        if body.get("code") != "Ok" or not body.get("routes"):
            raise UpstreamServiceError("osrm", f"Aucun itinéraire trouvé (code={body.get('code')})")

        route = body["routes"][0]
        legs = [
            RouteLeg(
                distance_km=leg["distance"] / 1000.0,
                duree_min=leg["duration"] / 60.0,
            )
            for leg in route["legs"]
        ]
        return Route(
            distance_km=route["distance"] / 1000.0,
            duree_min=route["duration"] / 60.0,
            legs=legs,
        )

    def calculer_matrice(
        self, points: list[tuple[float, float]]
    ) -> tuple[list[list[float]], list[list[float]]]:
        """Matrices routières point à point (service `/table`) : distances en km, durées en min.

        :raises UpstreamServiceError: OSRM injoignable, en erreur, ou matrice incomplète.
        """
        coords = ";".join(f"{lon},{lat}" for lat, lon in points)
        url = f"{self._base_url}/table/v1/driving/{coords}"
        try:
            response = httpx.get(
                url, params={"annotations": "distance,duration"}, timeout=self._timeout_s
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Appel OSRM /table échoué : %s", exc)
            raise UpstreamServiceError("osrm", str(exc)) from exc

        body = response.json()
        distances = body.get("distances")
        durees = body.get("durations")
        if body.get("code") != "Ok" or not distances or not durees:
            raise UpstreamServiceError("osrm", f"Matrice indisponible (code={body.get('code')})")
        if any(v is None for ligne in distances + durees for v in ligne):
            raise UpstreamServiceError("osrm", "Matrice incomplète (points non routables)")
        return (
            [[v / 1000.0 for v in ligne] for ligne in distances],
            [[v / 60.0 for v in ligne] for ligne in durees],
        )
