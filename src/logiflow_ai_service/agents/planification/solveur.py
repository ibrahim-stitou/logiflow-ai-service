"""Solveur déterministe de l'agent de planification.

1. compatibilité entre dossiers (groupable, ADR, carrosserie, température, international) ;
2. ordre des arrêts : insertion au moindre surcoût avec précédence (chargement avant
   déchargement), puis amélioration par déplacements successifs ;
3. groupes candidats : insertion gloutonne à partir de chaque dossier, sous contraintes de
   capacité, de fenêtres horaires et de durée ;
4. ressources : support de charge le plus petit qui convient, chauffeurs affectables les plus
   proches du premier chargement ;
5. sélection de N options distinctes selon des objectifs différents.
"""

from dataclasses import dataclass, field
from datetime import datetime

from logiflow_ai_service.agents.planification.horaires import (
    AMPLITUDE_MAX_EQUIPAGE_MIN,
    Evenement,
    Tournee,
    ordonnancer,
)
from logiflow_ai_service.agents.planification.matrice import Matrice, haversine_km
from logiflow_ai_service.agents.planification.schemas import (
    Chauffeur,
    DossierAPlanifier,
    PlanificationRequest,
    Remorque,
    Vehicule,
)

TAILLE_MAX_GROUPE = 8
ECART_TEMPERATURE_MAX = 2.0
COUT_KM = 1.15
COUT_HEURE_CHAUFFEUR = 32.0
PERMIS_PAR_TYPE = {"TRACTEUR": "CE", "PORTEUR": "C", "FOURGON": "B"}
# Catégories couvertes par chaque catégorie de permis (C couvre C1, CE couvre C, etc.).
COUVERTURE_PERMIS = {
    "B": {"B"},
    "C1": {"B", "C1"},
    "C": {"B", "C1", "C"},
    "C1E": {"B", "C1", "C1E"},
    "CE": {"B", "C1", "C", "C1E", "CE"},
}
TYPES_MONO_DOSSIER = {"SIMPLE", "NAVETTE"}


# ─── Compatibilité ───────────────────────────────────────────────────────


def compatibles(a: DossierAPlanifier, b: DossierAPlanifier, type_voyage: str) -> bool:
    if not (a.groupable and b.groupable):
        return False
    if a.contient_adr != b.contient_adr or a.international != b.international:
        return False
    carrosseries = {a.carrosserie_requise, b.carrosserie_requise} - {None}
    if len(carrosseries) > 1:
        return False
    if (a.temperature_requise is None) != (b.temperature_requise is None):
        return False
    if (
        a.temperature_requise is not None
        and abs(a.temperature_requise - b.temperature_requise) > ECART_TEMPERATURE_MAX
    ):
        return False
    if type_voyage == "RAMASSE" and a.dechargement.site_id != b.dechargement.site_id:
        return False
    return not (type_voyage == "DISTRIBUTION" and a.chargement.site_id != b.chargement.site_id)


# ─── Supports de charge et chauffeurs ────────────────────────────────────


@dataclass(frozen=True)
class Support:
    vehicule: Vehicule
    remorque: Remorque | None

    @property
    def charge_kg(self) -> float:
        return self.remorque.charge_utile_kg if self.remorque else self.vehicule.charge_utile_kg

    @property
    def volume_m3(self) -> float | None:
        return self.remorque.volume_utile_m3 if self.remorque else self.vehicule.volume_utile_m3

    @property
    def palettes(self) -> int:
        if self.remorque:
            return self.remorque.nb_positions_palettes
        return self.vehicule.nb_positions_palettes or 0

    @property
    def carrosserie(self) -> str | None:
        return self.remorque.carrosserie if self.remorque else self.vehicule.carrosserie

    @property
    def groupe_froid(self) -> bool:
        return self.remorque.groupe_froid if self.remorque else self.vehicule.groupe_froid

    @property
    def plage(self) -> tuple[float | None, float | None]:
        source = self.remorque or self.vehicule
        return source.temperature_min, source.temperature_max

    @property
    def permis_requis(self) -> str | None:
        return PERMIS_PAR_TYPE.get(self.vehicule.type)

    @property
    def libelle(self) -> str:
        if self.remorque:
            return f"{self.vehicule.immatriculation} + {self.remorque.immatriculation}"
        return self.vehicule.immatriculation


def supports_disponibles(requete: PlanificationRequest) -> list[Support]:
    """Tracteur + remorque (premier tracteur libre pour chaque remorque), ou porteur seul."""
    supports: list[Support] = []
    tracteurs = [v for v in requete.vehicules if v.type == "TRACTEUR"]
    if tracteurs:
        supports.extend(Support(tracteurs[0], r) for r in requete.remorques)
    supports.extend(Support(v, None) for v in requete.vehicules if v.type != "TRACTEUR")
    return sorted(supports, key=lambda s: s.charge_kg)


def support_convient(
    support: Support, dossiers: list[DossierAPlanifier], charge_max: float, volume_max: float
) -> bool:
    if support.charge_kg <= 0 or charge_max > support.charge_kg:
        return False
    if support.volume_m3 and volume_max > support.volume_m3:
        return False
    palettes = sum(d.nb_palettes for d in dossiers)
    if support.palettes and palettes > support.palettes:
        return False
    for d in dossiers:
        if d.carrosserie_requise and support.carrosserie != d.carrosserie_requise:
            return False
        if d.temperature_requise is not None:
            tmin, tmax = support.plage
            if not support.groupe_froid:
                return False
            if (tmin is not None and d.temperature_requise < tmin) or (
                tmax is not None and d.temperature_requise > tmax
            ):
                return False
    return True


def chauffeur_convient(
    chauffeur: Chauffeur,
    permis: str | None,
    adr: bool,
    international: bool,
    conduite_min: float,
) -> bool:
    if permis and chauffeur.categories_permis:
        couvertes = set().union(
            *(COUVERTURE_PERMIS.get(c, {c}) for c in chauffeur.categories_permis)
        )
        if permis not in couvertes:
            return False
    if adr and "ADR_BASE" not in chauffeur.habilitations:
        return False
    if international and not chauffeur.passeport_valide:
        return False
    return chauffeur.solde_temps_conduite_minutes >= conduite_min


# ─── Proposition ─────────────────────────────────────────────────────────


@dataclass
class Proposition:
    dossiers: list[DossierAPlanifier]
    tournee: Tournee
    support: Support | None = None
    chauffeurs: list[Chauffeur] = field(default_factory=list)
    charge_max_kg: float = 0.0
    volume_max_m3: float = 0.0
    alertes: list[str] = field(default_factory=list)

    @property
    def cle(self) -> frozenset[str]:
        return frozenset(d.id for d in self.dossiers)

    @property
    def poids_kg(self) -> float:
        return sum(d.poids_brut_kg for d in self.dossiers)

    @property
    def taux_poids(self) -> float:
        return self.charge_max_kg / self.support.charge_kg if self.support else 0.0

    @property
    def taux_volume(self) -> float:
        if not self.support or not self.support.volume_m3:
            return 0.0
        return self.volume_max_m3 / self.support.volume_m3

    @property
    def taux_remplissage(self) -> float:
        return max(self.taux_poids, self.taux_volume)

    @property
    def cout(self) -> float:
        heures = self.tournee.duree_totale_min / 60.0
        return self.tournee.distance_km * COUT_KM + heures * COUT_HEURE_CHAUFFEUR * max(
            1, len(self.chauffeurs)
        )

    @property
    def cout_par_tonne(self) -> float:
        return self.cout / max(self.poids_kg / 1000.0, 0.1)


def evenements_dossier(d: DossierAPlanifier) -> tuple[Evenement, Evenement]:
    return (
        Evenement(d.id, d.chargement.site_id, True, d.chargement.debut, d.chargement.fin),
        Evenement(d.id, d.dechargement.site_id, False, d.dechargement.debut, d.dechargement.fin),
    )


def _precedence_ok(sequence: list[Evenement]) -> bool:
    charges: set[str] = set()
    for ev in sequence:
        if ev.charge:
            charges.add(ev.dossier_id)
        elif ev.dossier_id not in charges:
            return False
    return True


class Solveur:
    def __init__(self, requete: PlanificationRequest, matrice: Matrice) -> None:
        self.requete = requete
        self.matrice = matrice
        self.sites = {s.id: s for s in requete.sites}
        self.supports = supports_disponibles(requete)
        self._cache: dict[frozenset[str], tuple[list[Evenement], Tournee]] = {}

    # --- ordre des arrêts -------------------------------------------------

    def _tournee(self, sequence: list[Evenement]) -> Tournee:
        return ordonnancer(sequence, self.matrice, self.requete.debut)

    def meilleure_sequence(
        self, dossiers: list[DossierAPlanifier]
    ) -> tuple[list[Evenement], Tournee]:
        cle = frozenset(d.id for d in dossiers)
        if cle not in self._cache:
            self._cache[cle] = self._calculer_sequence(dossiers)
        return self._cache[cle]

    def _calculer_sequence(
        self, dossiers: list[DossierAPlanifier]
    ) -> tuple[list[Evenement], Tournee]:
        ordonnes = sorted(dossiers, key=lambda d: (d.chargement.debut, d.id))
        sequence = list(evenements_dossier(ordonnes[0]))
        for d in ordonnes[1:]:
            sequence = self._inserer(sequence, *evenements_dossier(d))
        return self._ameliorer(sequence)

    def _inserer(
        self, sequence: list[Evenement], charge: Evenement, decharge: Evenement
    ) -> list[Evenement]:
        meilleure: list[Evenement] | None = None
        meilleur_cout = float("inf")
        for i in range(len(sequence) + 1):
            avec_charge = sequence[:i] + [charge] + sequence[i:]
            for j in range(i + 1, len(avec_charge) + 1):
                candidate = avec_charge[:j] + [decharge] + avec_charge[j:]
                cout = self._tournee(candidate).cout()
                if cout < meilleur_cout:
                    meilleure, meilleur_cout = candidate, cout
        return meilleure

    def _ameliorer(self, sequence: list[Evenement]) -> tuple[list[Evenement], Tournee]:
        """Déplace un événement à la fois tant que cela réduit le coût (précédence respectée)."""
        tournee = self._tournee(sequence)
        ameliore = True
        while ameliore:
            ameliore = False
            for i in range(len(sequence)):
                reste = sequence[:i] + sequence[i + 1 :]
                for j in range(len(reste) + 1):
                    if j == i:
                        continue
                    candidate = reste[:j] + [sequence[i]] + reste[j:]
                    if not _precedence_ok(candidate):
                        continue
                    essai = self._tournee(candidate)
                    if essai.cout() < tournee.cout() - 1e-6:
                        sequence, tournee, ameliore = candidate, essai, True
                        break
                if ameliore:
                    break
        return sequence, tournee

    # --- charge et ressources --------------------------------------------

    @staticmethod
    def charges_max(tournee: Tournee, dossiers: list[DossierAPlanifier]) -> tuple[float, float]:
        par_id = {d.id: d for d in dossiers}
        poids = volume = poids_max = volume_max = 0.0
        for arret in tournee.arrets:
            for did in arret.decharges:
                poids -= par_id[did].poids_brut_kg
                volume -= par_id[did].volume_m3
            for did in arret.charges:
                poids += par_id[did].poids_brut_kg
                volume += par_id[did].volume_m3
            poids_max, volume_max = max(poids_max, poids), max(volume_max, volume)
        return poids_max, volume_max

    def capacite_plafond(self, dossiers: list[DossierAPlanifier]) -> float:
        """Plus grande charge utile d'un support compatible avec ces dossiers (0 = aucun)."""
        compatibles_ = [s for s in self.supports if support_convient(s, dossiers, 0, 0)]
        return max((s.charge_kg for s in compatibles_), default=0.0)

    def _choisir_chauffeurs(self, proposition: Proposition, premier_site: str) -> list[Chauffeur]:
        dossiers = proposition.dossiers
        nb = proposition.tournee.chauffeurs_requis
        conduite_par_chauffeur = proposition.tournee.conduite_min / nb
        adr = any(d.contient_adr for d in dossiers)
        international = any(d.international for d in dossiers)
        permis = proposition.support.permis_requis if proposition.support else None
        eligibles = [
            c
            for c in self.requete.chauffeurs
            if chauffeur_convient(c, permis, adr, international, conduite_par_chauffeur)
        ]
        origine = self.sites.get(premier_site)

        def eloignement(c: Chauffeur) -> float:
            base = self.sites.get(c.site_rattachement_id or "")
            if origine is None or base is None:
                return 10_000.0
            return haversine_km(
                (base.latitude, base.longitude), (origine.latitude, origine.longitude)
            )

        return sorted(eligibles, key=lambda c: (eloignement(c), c.matricule))[:nb]

    def equiper(self, dossiers: list[DossierAPlanifier]) -> Proposition | None:
        _, tournee = self.meilleure_sequence(dossiers)
        charge_max, volume_max = self.charges_max(tournee, dossiers)
        proposition = Proposition(
            dossiers, tournee, charge_max_kg=charge_max, volume_max_m3=volume_max
        )
        support = next(
            (s for s in self.supports if support_convient(s, dossiers, charge_max, volume_max)),
            None,
        )
        if support is None:
            return None
        proposition.support = support
        proposition.chauffeurs = self._choisir_chauffeurs(proposition, tournee.arrets[0].site_id)
        if not proposition.chauffeurs:
            return None
        if len(proposition.chauffeurs) < tournee.chauffeurs_requis:
            proposition.alertes.append(
                "Durée de conduite ou amplitude élevée : un second chauffeur est recommandé "
                "mais aucun n'est disponible"
            )
        if tournee.duree_totale_min > AMPLITUDE_MAX_EQUIPAGE_MIN:
            proposition.alertes.append(
                "Voyage de plus d'une journée : prévoir le repos journalier de l'équipage"
            )
        if tournee.fenetres_manquees:
            proposition.alertes.append(
                f"{tournee.fenetres_manquees} fenêtre(s) horaire(s) non respectée(s)"
            )
        if tournee.arrivee > self.requete.fin:
            proposition.alertes.append("Arrivée prévue après la fin de la période demandée")
        return proposition

    # --- groupes candidats -----------------------------------------------

    def groupe_depuis(
        self, graine: DossierAPlanifier, dossiers: list[DossierAPlanifier]
    ) -> list[DossierAPlanifier]:
        groupe = [graine]
        if self.requete.type_voyage in TYPES_MONO_DOSSIER:
            return groupe
        plafond = self.capacite_plafond(groupe)
        _, tournee = self.meilleure_sequence(groupe)
        while len(groupe) < TAILLE_MAX_GROUPE:
            meilleur: tuple[float, DossierAPlanifier, Tournee] | None = None
            for d in dossiers:
                if d in groupe or not all(
                    compatibles(d, g, self.requete.type_voyage) for g in groupe
                ):
                    continue
                essai_groupe = groupe + [d]
                _, essai = self.meilleure_sequence(essai_groupe)
                if essai.fenetres_manquees or essai.duree_totale_min > AMPLITUDE_MAX_EQUIPAGE_MIN:
                    continue
                charge_max, _ = self.charges_max(essai, essai_groupe)
                if charge_max > min(plafond, self.capacite_plafond(essai_groupe)):
                    continue
                _, seul = self.meilleure_sequence([d])
                surcout = essai.conduite_min - tournee.conduite_min
                # Le groupage doit coûter moins de conduite qu'un voyage dédié.
                if surcout >= seul.conduite_min:
                    continue
                if meilleur is None or surcout < meilleur[0]:
                    meilleur = (surcout, d, essai)
            if meilleur is None:
                break
            groupe.append(meilleur[1])
            tournee = meilleur[2]
        return groupe

    def propositions(self) -> tuple[list[Proposition], list[str]]:
        dossiers = [
            d
            for d in self.requete.dossiers
            if d.chargement.site_id in self.sites and d.dechargement.site_id in self.sites
        ]
        vues: dict[frozenset[str], Proposition] = {}
        for graine in sorted(dossiers, key=lambda d: d.chargement.debut):
            groupe = self.groupe_depuis(graine, dossiers)
            cle = frozenset(d.id for d in groupe)
            if cle in vues:
                continue
            proposition = self.equiper(groupe)
            if proposition is None and len(groupe) > 1:
                proposition = self.equiper([graine])
            if proposition is not None:
                vues.setdefault(proposition.cle, proposition)
        couverts = set().union(*vues.keys()) if vues else set()
        non_planifiables = [d.reference for d in self.requete.dossiers if d.id not in couverts]
        return list(vues.values()), non_planifiables


# ─── Sélection des options ───────────────────────────────────────────────

OBJECTIFS = [
    ("REMPLISSAGE", "Remplissage maximal", lambda p: (-p.taux_remplissage, p.cout)),
    ("ECONOMIE", "Coût à la tonne minimal", lambda p: (p.cout_par_tonne, -len(p.dossiers))),
    ("COUVERTURE", "Le plus de dossiers servis", lambda p: (-len(p.dossiers), p.cout)),
    (
        "EQUILIBRE",
        "Compromis remplissage / coût",
        lambda p: (-(p.taux_remplissage * 100) + p.cout_par_tonne / 10, p.cout),
    ),
    ("PONCTUALITE", "Départ le plus tôt", lambda p: (p.tournee.depart, p.cout)),
]


@dataclass
class OptionRetenue:
    objectif: str
    libelle_objectif: str
    proposition: Proposition


def selectionner(propositions: list[Proposition], nb_options: int) -> list[OptionRetenue]:
    """Une option par objectif, toutes distinctes.

    Si le meilleur candidat d'un objectif est déjà retenu, l'option suivante est présentée comme
    une alternative : son libellé ne doit pas prétendre qu'elle est la meilleure sur ce critère.
    """
    retenues: list[OptionRetenue] = []
    deja: set[frozenset[str]] = set()
    for code, libelle, cle in OBJECTIFS:
        if len(retenues) >= nb_options:
            break
        classement = sorted(propositions, key=cle)
        for rang, proposition in enumerate(classement):
            if proposition.cle not in deja:
                intitule = libelle if rang == 0 else f"Alternative ({libelle.lower()})"
                retenues.append(OptionRetenue(code, intitule, proposition))
                deja.add(proposition.cle)
                break
    return retenues


def depart_arrivee(proposition: Proposition) -> tuple[datetime, datetime]:
    return proposition.tournee.depart, proposition.tournee.arrivee
