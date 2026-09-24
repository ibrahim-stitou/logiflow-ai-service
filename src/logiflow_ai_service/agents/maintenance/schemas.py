"""Contrat POST /internal/ai/v1/maintenance/recommander (voir docs/integration-ia.md côté backend).

Spring envoie l'état de chaque véhicule (compteurs, plans d'entretien, ordres de travail,
documents, activité réalisée et voyages planifiés) ; l'agent renvoie un score de santé, les
échéances projetées, les anomalies et des recommandations priorisées avec un créneau libre.
"""

from datetime import date, datetime

from pydantic import Field

from logiflow_ai_service.schemas import CamelModel


class Plan(CamelModel):
    id: str
    libelle: str
    periodicite_km: int | None = None
    periodicite_mois: int | None = None
    seuil_alerte_km: int = 0
    duree_estimee_min: int = 0


class Ordre(CamelModel):
    type: str
    statut: str
    date_planifiee: datetime | None = None


class Document(CamelModel):
    type: str
    date_expiration: date | None = None


class VoyagePlanifie(CamelModel):
    reference: str
    depart: datetime
    arrivee: datetime
    distance_km: float = 0


class VehiculeAAnalyser(CamelModel):
    id: str
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
