"""Matrice des distances et durées entre sites, routière (OSRM) ou estimée (Haversine)."""

import logging
import math
from dataclasses import dataclass

from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError
from logiflow_ai_service.infrastructure.osrm_client import OsrmClient

logger = logging.getLogger(__name__)

RAYON_TERRE_KM = 6371.0088
# Repli sans OSRM : la route est ~30 % plus longue que le vol d'oiseau, poids lourd à 70 km/h.
COEFFICIENT_DETOUR = 1.3
VITESSE_MOYENNE_KMH = 70.0


@dataclass(frozen=True)
class Matrice:
    index: dict[str, int]
    distances_km: list[list[float]]
    durees_min: list[list[float]]
    source: str

    def km(self, de: str, vers: str) -> float:
        return self.distances_km[self.index[de]][self.index[vers]]

    def minutes(self, de: str, vers: str) -> float:
        return self.durees_min[self.index[de]][self.index[vers]]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * RAYON_TERRE_KM * math.asin(math.sqrt(h))


def matrice_haversine(points: dict[str, tuple[float, float]]) -> Matrice:
    ids = list(points)
    distances = [
        [haversine_km(points[i], points[j]) * COEFFICIENT_DETOUR for j in ids] for i in ids
    ]
    durees = [[d / VITESSE_MOYENNE_KMH * 60.0 for d in ligne] for ligne in distances]
    return Matrice({s: k for k, s in enumerate(ids)}, distances, durees, "HAVERSINE")


def construire_matrice(osrm: OsrmClient | None, points: dict[str, tuple[float, float]]) -> Matrice:
    """Matrice routière OSRM, ou estimation Haversine si OSRM est indisponible."""
    ids = list(points)
    if osrm is not None and len(ids) >= 2:
        try:
            distances, durees = osrm.calculer_matrice([points[i] for i in ids])
            return Matrice({s: k for k, s in enumerate(ids)}, distances, durees, "OSRM")
        except UpstreamServiceError as exc:
            logger.info("OSRM indisponible, repli Haversine : %s", exc)
    return matrice_haversine(points)
