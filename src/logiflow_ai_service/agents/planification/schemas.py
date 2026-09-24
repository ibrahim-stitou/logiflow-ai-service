"""Contrat POST /internal/ai/v1/planification/proposer (voir docs/integration-ia.md côté backend).

Spring envoie un contexte déjà filtré : dossiers `CREE` de la période, sites utilisés, et
ressources libres et conformes sur la période. L'agent ne fait aucun appel au backend.
"""

from datetime import datetime

from pydantic import Field

from logiflow_ai_service.schemas import CamelModel


class FenetreSite(CamelModel):
    site_id: str
    debut: datetime
    fin: datetime


class DossierAPlanifier(CamelModel):
    id: str
    reference: str
    poids_brut_kg: float
    volume_m3: float
    nb_palettes: int = 0
    contient_adr: bool = False
    groupable: bool = True
    international: bool = False
    carrosserie_requise: str | None = None
    temperature_requise: float | None = None
    chargement: FenetreSite
    dechargement: FenetreSite


class Site(CamelModel):
    id: str
    libelle: str
    latitude: float
    longitude: float


class Vehicule(CamelModel):
    id: str
    immatriculation: str
    type: str
    charge_utile_kg: float
    volume_utile_m3: float | None = None
    nb_positions_palettes: int | None = None
    carrosserie: str | None = None
    groupe_froid: bool = False
    temperature_min: float | None = None
    temperature_max: float | None = None


class Remorque(CamelModel):
    id: str
    immatriculation: str
    carrosserie: str | None = None
    charge_utile_kg: float
    volume_utile_m3: float
    nb_positions_palettes: int = 0
    groupe_froid: bool = False
    temperature_min: float | None = None
    temperature_max: float | None = None


class Chauffeur(CamelModel):
    id: str
    matricule: str
    nom: str
    prenom: str
    solde_temps_conduite_minutes: int
    categories_permis: list[str] = Field(default_factory=list)
    habilitations: list[str] = Field(default_factory=list)
    passeport_valide: bool = False
    site_rattachement_id: str | None = None


class PlanificationRequest(CamelModel):
    debut: datetime
    fin: datetime
    type_voyage: str = "GROUPAGE"
    nb_options: int = Field(default=3, ge=1, le=5)
    dossiers: list[DossierAPlanifier]
    sites: list[Site]
    vehicules: list[Vehicule] = Field(default_factory=list)
    remorques: list[Remorque] = Field(default_factory=list)
    chauffeurs: list[Chauffeur] = Field(default_factory=list)
    correlation_id: str | None = None


class ArretPropose(CamelModel):
    ordre: int
    site_id: str
    libelle: str
    latitude: float
    longitude: float
    dossiers_charges: list[str]
    dossiers_decharges: list[str]
    eta: datetime
    etd: datetime
    distance_depuis_precedent_km: float
    duree_depuis_precedent_min: float
    charge_apres_kg: float
    attente_min: float = 0
    fenetre_respectee: bool = True


class Indicateurs(CamelModel):
    nb_dossiers: int
    distance_km: float
    duree_conduite_min: int
    duree_totale_min: int
    poids_kg: float
    volume_m3: float
    palettes: int
    taux_remplissage_poids: float
    taux_remplissage_volume: float
    fenetres_manquees: int
    cout_estime: float
    cout_par_tonne: float | None = None


class OptionVoyage(CamelModel):
    rang: int
    objectif: str
    libelle_objectif: str
    type_voyage: str
    dossier_ids: list[str]
    arrets: list[ArretPropose]
    vehicule_id: str | None
    remorque_id: str | None
    chauffeur_ids: list[str]
    depart_prevu: datetime
    arrivee_prevue: datetime
    indicateurs: Indicateurs
    alertes: list[str] = Field(default_factory=list)
    justification: str = ""
    recommandee: bool = False


class PlanificationResponse(CamelModel):
    options: list[OptionVoyage] = Field(default_factory=list)
    comparaison: str = ""
    dossiers_non_planifiables: list[str] = Field(default_factory=list)
    source_distances: str = "OSRM"
    source_redaction: str = "GABARIT"
