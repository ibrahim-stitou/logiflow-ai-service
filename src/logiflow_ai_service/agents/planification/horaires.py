"""Ordonnancement d'une tournée : heures d'arrivée et de départ à chaque arrêt.

Règles (simplifiées, inspirées du règlement CE 561/2006) :
- temps de service fixe à chaque arrêt (chargement ou déchargement) ;
- pause de 45 min après chaque tranche de 4 h 30 de conduite cumulée ;
- attente sur place si l'on arrive avant l'ouverture de la fenêtre horaire ;
- au-delà de 9 h de conduite ou 13 h d'amplitude, un second chauffeur est requis.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from logiflow_ai_service.agents.planification.matrice import Matrice

SERVICE_MIN = 45.0
CONDUITE_AVANT_PAUSE_MIN = 270.0
PAUSE_MIN = 45.0
CONDUITE_MAX_UN_CHAUFFEUR_MIN = 540.0
AMPLITUDE_MAX_UN_CHAUFFEUR_MIN = 780.0
AMPLITUDE_MAX_EQUIPAGE_MIN = 1260.0


@dataclass(frozen=True)
class Evenement:
    """Chargement (`charge=True`) ou déchargement d'un dossier sur un site."""

    dossier_id: str
    site_id: str
    charge: bool
    debut: datetime
    fin: datetime


@dataclass
class ArretPlanifie:
    site_id: str
    charges: list[str] = field(default_factory=list)
    decharges: list[str] = field(default_factory=list)
    ouverture: datetime | None = None
    fermeture: datetime | None = None
    eta: datetime | None = None
    etd: datetime | None = None
    distance_km: float = 0.0
    duree_min: float = 0.0
    attente_min: float = 0.0
    fenetre_respectee: bool = True


@dataclass
class Tournee:
    arrets: list[ArretPlanifie]
    distance_km: float
    conduite_min: float
    duree_totale_min: float
    fenetres_manquees: int

    @property
    def depart(self) -> datetime:
        return self.arrets[0].eta

    @property
    def arrivee(self) -> datetime:
        return self.arrets[-1].etd

    @property
    def chauffeurs_requis(self) -> int:
        if (
            self.conduite_min > CONDUITE_MAX_UN_CHAUFFEUR_MIN
            or self.duree_totale_min > AMPLITUDE_MAX_UN_CHAUFFEUR_MIN
        ):
            return 2
        return 1

    def cout(self) -> float:
        """Coût d'optimisation : durée totale, fortement pénalisée par les fenêtres manquées."""
        return self.duree_totale_min + self.fenetres_manquees * 1000.0


def regrouper_en_arrets(evenements: list[Evenement]) -> list[ArretPlanifie]:
    """Fusionne les événements consécutifs sur un même site en un seul arrêt."""
    arrets: list[ArretPlanifie] = []
    for ev in evenements:
        if not arrets or arrets[-1].site_id != ev.site_id:
            arrets.append(ArretPlanifie(site_id=ev.site_id))
        arret = arrets[-1]
        (arret.charges if ev.charge else arret.decharges).append(ev.dossier_id)
        arret.ouverture = ev.debut if arret.ouverture is None else max(arret.ouverture, ev.debut)
        arret.fermeture = ev.fin if arret.fermeture is None else min(arret.fermeture, ev.fin)
    return arrets


def ordonnancer(
    evenements: list[Evenement], matrice: Matrice, depart_au_plus_tot: datetime
) -> Tournee:
    arrets = regrouper_en_arrets(evenements)
    conduite = 0.0
    distance = 0.0
    manquees = 0
    precedent: ArretPlanifie | None = None
    for arret in arrets:
        if precedent is None:
            arrivee = max(depart_au_plus_tot, arret.ouverture)
        else:
            trajet_min = matrice.minutes(precedent.site_id, arret.site_id)
            pauses = int((conduite + trajet_min) // CONDUITE_AVANT_PAUSE_MIN) - int(
                conduite // CONDUITE_AVANT_PAUSE_MIN
            )
            arret.distance_km = matrice.km(precedent.site_id, arret.site_id)
            arret.duree_min = trajet_min
            conduite += trajet_min
            distance += arret.distance_km
            arrivee = precedent.etd + timedelta(minutes=trajet_min + pauses * PAUSE_MIN)
        debut_service = arrivee
        if arrivee < arret.ouverture:
            arret.attente_min = (arret.ouverture - arrivee).total_seconds() / 60.0
            debut_service = arret.ouverture
        if arret.ouverture >= arret.fermeture or debut_service >= arret.fermeture:
            arret.fenetre_respectee = False
            manquees += 1
        arret.eta = arrivee
        arret.etd = debut_service + timedelta(minutes=SERVICE_MIN)
        precedent = arret
    duree_totale = (arrets[-1].etd - arrets[0].eta).total_seconds() / 60.0
    return Tournee(arrets, distance, conduite, duree_totale, manquees)
