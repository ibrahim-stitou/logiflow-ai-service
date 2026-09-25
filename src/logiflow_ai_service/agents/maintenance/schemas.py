"""Contrat POST /internal/ai/v1/maintenance/recommander (voir docs/integration-ia.md côté backend).

Spring envoie l'état de chaque engin, véhicule ou remorque : compteurs, plans d'entretien avec
leur échéance calculée par le module maintenance, ordres de travail, documents, sinistres des
12 derniers mois, activité réalisée et voyages planifiés. L'agent renvoie un score de santé, les
échéances projetées, les anomalies et des recommandations priorisées avec un créneau libre.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from logiflow_ai_service.schemas import CamelModel


class Plan(CamelModel):
    id: str
    libelle: str
    type: str = "ENTRETIEN_PREVENTIF"
    periodicite_km: int | None = None
    periodicite_mois: int | None = None
    periodicite_heures: int | None = None
    seuil_alerte_km: int = 0
    duree_estimee_min: int = 0
    # Dernière réalisation et échéance calculées par Spring (absentes : estimation par l'agent).
    derniere_date: date | None = None
    derniere_km: int | None = None
    km_restant: int | None = None
    date_echeance: date | None = None
    etat: str | None = None


class Ordre(CamelModel):
    reference: str | None = None
    type: str
    nature: str | None = None
    statut: str
    origine: str | None = None
    plan_id: str | None = None
    date_planifiee: datetime | None = None
    immobilisation: bool = False
    cout_ttc: Decimal | None = None


class Sinistre(CamelModel):
    reference: str
    date_survenance: date
    type: str
    gravite: str
    responsabilite: str = "A_DETERMINER"
    statut: str
    engin_immobilise: bool = False
    cout_net: Decimal | None = None


class Document(CamelModel):
    type: str
    date_expiration: date | None = None


class VoyagePlanifie(CamelModel):
    reference: str
    depart: datetime
    arrivee: datetime
    distance_km: float = 0


class VehiculeAAnalyser(CamelModel):
    """Engin à analyser : pour une remorque, `type` est la carrosserie et `heures_moteur` les
    heures du groupe froid."""

    id: str
    type_engin: str = "VEHICULE"
    immatriculation: str
    type: str
    statut: str
    kilometrage: int = 0
    heures_moteur: int = 0
    annee_mise_en_circulation: int | None = None
    # Activité des 90 derniers jours (voyages réalisés et carburant).
    km_realises: float = 0
    litres_consommes: float = 0
    plans: list[Plan] = Field(default_factory=list)
    ordres: list[Ordre] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    sinistres: list[Sinistre] = Field(default_factory=list)
    voyages_planifies: list[VoyagePlanifie] = Field(default_factory=list)


class MaintenanceRequest(CamelModel):
    date_reference: datetime
    horizon_jours: int = Field(default=30, ge=1, le=180)
    vehicules: list[VehiculeAAnalyser]
    correlation_id: str | None = None


class Echeance(CamelModel):
    libelle: str
    km_restant: int | None = None
    date_echeance: date | None = None
    en_alerte: bool = False


class Recommandation(CamelModel):
    type: str
    libelle: str
    priorite: str
    avant_le: date | None = None
    creneau_debut: datetime | None = None
    creneau_fin: datetime | None = None
    duree_min: int = 0
    justification: str = ""
    deja_planifie: bool = False


class AnalyseVehicule(CamelModel):
    vehicule_id: str
    type_engin: str = "VEHICULE"
    immatriculation: str
    score: float
    statut: str
    km_par_jour: float
    consommation_l100: float | None = None
    km_avant_echeance: int | None = None
    date_echeance: date | None = None
    echeances: list[Echeance] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    recommandations: list[Recommandation] = Field(default_factory=list)
    explication: str = ""


class MaintenanceResponse(CamelModel):
    vehicules: list[AnalyseVehicule] = Field(default_factory=list)
    synthese: str = ""
    source_redaction: str = "GABARIT"
