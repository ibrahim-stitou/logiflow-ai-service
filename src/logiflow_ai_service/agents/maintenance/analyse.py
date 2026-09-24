"""Analyse déterministe de l'état d'un véhicule : usage, échéances, anomalies, score, actions.

Hypothèses (données disponibles dans le TMS) :
- l'usage réel est estimé par les kilomètres des voyages réalisés sur 90 jours ; sans activité,
  on retombe sur le kilométrage moyen depuis la mise en circulation (plafonné) ;
- les ordres de travail ne portent pas de kilométrage : la date du dernier entretien préventif
  terminé sert d'origine, et à défaut la position dans le cycle (kilométrage modulo périodicité) ;
- une échéance est avancée si les voyages déjà planifiés consomment les kilomètres restants.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import median

from logiflow_ai_service.agents.maintenance.schemas import (
    AnalyseVehicule,
    Echeance,
    MaintenanceRequest,
    Recommandation,
    VehiculeAAnalyser,
)

JOURS_ACTIVITE = 90
KM_PAR_JOUR_DEFAUT = 250.0
KM_PAR_JOUR_MAX = 900.0
JOURS_PAR_MOIS = 30.44
DUREE_INTERVENTION_DEFAUT_MIN = 240
FENETRE_REPARATIONS_JOURS = 180
SEUIL_REPARATIONS = 2
SURCONSOMMATION = 1.2
KM_MIN_POUR_CONSOMMATION = 300
DOCUMENTS_REGLEMENTAIRES = {
    "CONTROLE_TECHNIQUE": "Contrôle technique",
    "ASSURANCE": "Assurance",
    "CARTE_GRISE": "Carte grise",
    "ADR": "Agrément ADR",
}
STATUTS_ACTIFS = {"PLANIFIE", "EN_COURS"}
HEURE_ATELIER = time(7, 0)

PENALITE_ECHUE = 45
PENALITE_ALERTE = 25
PENALITE_HORIZON = 10
PENALITE_DOCUMENT_EXPIRE = 30
PENALITE_DOCUMENT_PROCHE = 10
PENALITE_REPARATIONS = 15
PENALITE_SURCONSOMMATION = 10
SCORE_MAX_DOCUMENT_EXPIRE = 39.0


@dataclass
class _Echeance:
    echeance: Echeance
    plan_duree_min: int
    deja_planifie: bool


def km_par_jour(v: VehiculeAAnalyser, aujourd_hui: date) -> float:
    if v.km_realises > 0:
        return v.km_realises / JOURS_ACTIVITE
    if v.annee_mise_en_circulation and v.kilometrage > 0:
        jours = max((aujourd_hui - date(v.annee_mise_en_circulation, 1, 1)).days, 365)
        return min(v.kilometrage / jours, KM_PAR_JOUR_MAX)
    return KM_PAR_JOUR_DEFAUT


def consommation_l100(v: VehiculeAAnalyser) -> float | None:
    if v.km_realises < KM_MIN_POUR_CONSOMMATION or v.litres_consommes <= 0:
        return None
    return round(v.litres_consommes / v.km_realises * 100, 1)


def _dernier(v: VehiculeAAnalyser, type_ot: str, statut: str) -> date | None:
    dates = [
        o.date_planifiee.date()
        for o in v.ordres
        if o.type == type_ot and o.statut == statut and o.date_planifiee
    ]
    return max(dates, default=None)


def _deja_planifie(v: VehiculeAAnalyser, type_ot: str, aujourd_hui: date) -> bool:
    return any(
        o.type == type_ot
        and o.statut in STATUTS_ACTIFS
        and (o.date_planifiee is None or o.date_planifiee.date() >= aujourd_hui - timedelta(days=7))
        for o in v.ordres
    )


def _km_planifies_avant(v: VehiculeAAnalyser, limite: date) -> float:
    return sum(p.distance_km for p in v.voyages_planifies if p.depart.date() <= limite)


def echeances_plans(v: VehiculeAAnalyser, aujourd_hui: date, horizon: int) -> list[_Echeance]:
    usage = km_par_jour(v, aujourd_hui)
    dernier_preventif = _dernier(v, "ENTRETIEN_PREVENTIF", "TERMINE")
    deja = _deja_planifie(v, "ENTRETIEN_PREVENTIF", aujourd_hui)
    resultat = []
    for plan in v.plans:
        km_restant = None
        dates: list[date] = []
        if plan.periodicite_km:
            if dernier_preventif:
                km_depuis = usage * (aujourd_hui - dernier_preventif).days
            else:
                km_depuis = v.kilometrage % plan.periodicite_km
            km_restant = round(plan.periodicite_km - km_depuis)
            date_km = aujourd_hui + timedelta(days=max(km_restant, 0) / max(usage, 1))
            # Les voyages déjà planifiés peuvent consommer le reste avant cette date.
            if _km_planifies_avant(v, date_km) >= km_restant > 0:
                premier = next(
                    (
                        p.depart.date()
                        for p in sorted(v.voyages_planifies, key=lambda p: p.depart)
                        if _km_planifies_avant(v, p.depart.date()) >= km_restant
                    ),
                    date_km,
                )
                date_km = min(date_km, premier)
            dates.append(date_km)
        if plan.periodicite_mois and dernier_preventif:
            dates.append(
                dernier_preventif + timedelta(days=round(plan.periodicite_mois * JOURS_PAR_MOIS))
            )
        date_echeance = min(dates, default=None)
        en_alerte = (km_restant is not None and km_restant <= plan.seuil_alerte_km) or (
            date_echeance is not None and date_echeance <= aujourd_hui + timedelta(days=horizon)
        )
        resultat.append(
            _Echeance(
                Echeance(
                    libelle=plan.libelle,
                    km_restant=km_restant,
                    date_echeance=date_echeance,
                    en_alerte=en_alerte,
                ),
                plan.duree_estimee_min or DUREE_INTERVENTION_DEFAUT_MIN,
                deja,
            )
        )
    return resultat


def creneau_libre(
    v: VehiculeAAnalyser, debut: datetime, avant: date | None, duree_min: int
) -> tuple[datetime, datetime] | None:
    """Premier créneau (à partir de 7 h) entre deux voyages planifiés, avant l'échéance."""
    duree = timedelta(minutes=duree_min)
    candidat = datetime.combine(debut.date() + timedelta(days=1), HEURE_ATELIER, tzinfo=UTC)
    limite = (
        datetime.combine(avant, time(23, 59), tzinfo=UTC)
        if avant
        else candidat + timedelta(days=60)
    )
    for voyage in sorted(v.voyages_planifies, key=lambda p: p.depart):
        if voyage.arrivee <= candidat:
            continue
        if candidat + duree <= voyage.depart:
            break
        candidat = max(candidat, voyage.arrivee)
        if candidat.time() > time(16, 0):
            candidat = datetime.combine(
                candidat.date() + timedelta(days=1), HEURE_ATELIER, tzinfo=UTC
            )
    if candidat + duree > limite and avant is not None and avant > debut.date():
        return None
    return candidat, candidat + duree


def _priorite(avant: date | None, aujourd_hui: date, echue: bool) -> str:
    if echue:
        return "URGENTE"
    if avant is not None and avant <= aujourd_hui + timedelta(days=7):
        return "HAUTE"
    return "NORMALE"


def statut_depuis_score(score: float, km_avant: int | None, bloquant: bool = False) -> str:
    """Statut dérivé comme `ScoreSante` côté Spring ; un document expiré immobilise le véhicule."""
    if bloquant or (km_avant is not None and km_avant <= 0):
        return "CRITIQUE"
    if score >= 80:
        return "BON"
    if score >= 60:
        return "SURVEILLER"
    if score >= 40:
        return "A_PLANIFIER"
    return "CRITIQUE"


def analyser_vehicule(
    v: VehiculeAAnalyser,
    requete: MaintenanceRequest,
    mediane_conso: dict[str, float],
) -> AnalyseVehicule:
    aujourd_hui = requete.date_reference.date()
    horizon = requete.horizon_jours
    usage = km_par_jour(v, aujourd_hui)
    conso = consommation_l100(v)
    penalites = 0
    document_expire = False
    anomalies: list[str] = []
    recommandations: list[Recommandation] = []

    echeances = echeances_plans(v, aujourd_hui, horizon)
    for e in echeances:
        ech = e.echeance
        echue = (ech.km_restant is not None and ech.km_restant <= 0) or (
            ech.date_echeance is not None and ech.date_echeance <= aujourd_hui
        )
        if echue:
            penalites += PENALITE_ECHUE
        elif ech.en_alerte:
            penalites += PENALITE_ALERTE
        if not (echue or ech.en_alerte):
            continue
        creneau = creneau_libre(v, requete.date_reference, ech.date_echeance, e.plan_duree_min)
        detail = []
        if ech.km_restant is not None:
            detail.append(f"{max(ech.km_restant, 0)} km restants")
        if ech.date_echeance:
            detail.append(f"échéance projetée le {ech.date_echeance.strftime('%d/%m/%Y')}")
        recommandations.append(
            Recommandation(
                type="ENTRETIEN_PREVENTIF",
                libelle=f"{ech.libelle} à réaliser",
                priorite=_priorite(ech.date_echeance, aujourd_hui, echue),
                avant_le=ech.date_echeance,
                creneau_debut=creneau[0] if creneau else None,
                creneau_fin=creneau[1] if creneau else None,
                duree_min=e.plan_duree_min,
                justification=", ".join(detail) + f" (usage ≈ {round(usage)} km/jour)",
                deja_planifie=e.deja_planifie,
            )
        )

    for doc in v.documents:
        libelle = DOCUMENTS_REGLEMENTAIRES.get(doc.type)
        if libelle is None or doc.date_expiration is None:
            continue
        expire = doc.date_expiration < aujourd_hui
        proche = doc.date_expiration <= aujourd_hui + timedelta(days=horizon)
        if not (expire or proche):
            continue
        penalites += PENALITE_DOCUMENT_EXPIRE if expire else PENALITE_DOCUMENT_PROCHE
        document_expire = document_expire or expire
        type_ot = "CONTROLE_TECHNIQUE" if doc.type == "CONTROLE_TECHNIQUE" else "AUTRE"
        creneau = (
            creneau_libre(v, requete.date_reference, doc.date_expiration, 120)
            if type_ot == "CONTROLE_TECHNIQUE"
            else None
        )
        recommandations.append(
            Recommandation(
                type=type_ot,
                libelle=f"{libelle} : {'expiré' if expire else 'à renouveler'}",
                priorite="URGENTE"
                if expire
                else _priorite(doc.date_expiration, aujourd_hui, False),
                avant_le=doc.date_expiration,
                creneau_debut=creneau[0] if creneau else None,
                creneau_fin=creneau[1] if creneau else None,
                duree_min=120 if creneau else 0,
                justification=(
                    f"Expire le {doc.date_expiration.strftime('%d/%m/%Y')} : "
                    "le véhicule ne peut pas être affecté à un voyage au-delà."
                ),
                deja_planifie=type_ot == "CONTROLE_TECHNIQUE"
                and _deja_planifie(v, "CONTROLE_TECHNIQUE", aujourd_hui),
            )
        )

    limite_reparations = aujourd_hui - timedelta(days=FENETRE_REPARATIONS_JOURS)
    reparations = [
        o
        for o in v.ordres
        if o.type == "REPARATION"
        and o.statut != "ANNULE"
        and o.date_planifiee
        and o.date_planifiee.date() >= limite_reparations
    ]
    if len(reparations) >= SEUIL_REPARATIONS:
        penalites += PENALITE_REPARATIONS
        anomalies.append(
            f"{len(reparations)} réparations en {FENETRE_REPARATIONS_JOURS} jours : "
            "panne récurrente possible"
        )
        recommandations.append(
            Recommandation(
                type="REPARATION",
                libelle="Diagnostic approfondi",
                priorite="HAUTE",
                duree_min=180,
                justification="Réparations répétées : rechercher une cause commune.",
                deja_planifie=_deja_planifie(v, "REPARATION", aujourd_hui),
            )
        )

    reference = mediane_conso.get(v.type)
    if conso is not None and reference and conso > reference * SURCONSOMMATION:
        penalites += PENALITE_SURCONSOMMATION
        ecart = round((conso / reference - 1) * 100)
        anomalies.append(
            f"Consommation de {conso} L/100 km, +{ecart} % par rapport aux "
            f"{v.type.lower()}s de la flotte ({reference} L/100 km)"
        )
        recommandations.append(
            Recommandation(
                type="ENTRETIEN_PREVENTIF",
                libelle="Contrôle injection, filtres, pneumatiques et freins",
                priorite="NORMALE",
                duree_min=120,
                justification="Surconsommation persistante sur 90 jours.",
            )
        )

    if v.statut in {"EN_MAINTENANCE", "IMMOBILISE"}:
        anomalies.append(f"Véhicule actuellement {v.statut.lower().replace('_', ' ')}")

    kms = [e.echeance.km_restant for e in echeances if e.echeance.km_restant is not None]
    dates = [e.echeance.date_echeance for e in echeances if e.echeance.date_echeance]
    km_avant = min(kms, default=None)
    score = float(max(0, min(100, 100 - penalites)))
    if document_expire:
        # Même statut CRITIQUE une fois le score enregistré par Spring (dérivé du score seul).
        score = min(score, SCORE_MAX_DOCUMENT_EXPIRE)
    ordre = {"URGENTE": 0, "HAUTE": 1, "NORMALE": 2}
    recommandations.sort(key=lambda r: (r.deja_planifie, ordre[r.priorite], r.avant_le or date.max))
    return AnalyseVehicule(
        vehicule_id=v.id,
        immatriculation=v.immatriculation,
        score=score,
        statut=statut_depuis_score(score, km_avant, document_expire),
        km_par_jour=round(usage, 1),
        consommation_l100=conso,
        km_avant_echeance=km_avant,
        date_echeance=min(dates, default=None),
        echeances=[e.echeance for e in echeances],
        anomalies=anomalies,
        recommandations=recommandations,
    )


def medianes_consommation(requete: MaintenanceRequest) -> dict[str, float]:
    par_type: dict[str, list[float]] = {}
    for v in requete.vehicules:
        conso = consommation_l100(v)
        if conso is not None:
            par_type.setdefault(v.type, []).append(conso)
    return {t: round(median(valeurs), 1) for t, valeurs in par_type.items() if len(valeurs) >= 3}


def analyser(requete: MaintenanceRequest) -> list[AnalyseVehicule]:
    medianes = medianes_consommation(requete)
    analyses = [analyser_vehicule(v, requete, medianes) for v in requete.vehicules]
    return sorted(analyses, key=lambda a: (a.score, a.immatriculation))
