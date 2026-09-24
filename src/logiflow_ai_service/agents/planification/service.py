"""Agent de planification de voyage : solveur déterministe + rédaction par LLM."""

import logging

from logiflow_ai_service.agents.planification.matrice import construire_matrice
from logiflow_ai_service.agents.planification.redaction import rediger
from logiflow_ai_service.agents.planification.schemas import (
    ArretPropose,
    Indicateurs,
    OptionVoyage,
    PlanificationRequest,
    PlanificationResponse,
)
from logiflow_ai_service.agents.planification.solveur import OptionRetenue, Solveur, selectionner
from logiflow_ai_service.infrastructure.llm_client import LlmClient
from logiflow_ai_service.infrastructure.osrm_client import OsrmClient

logger = logging.getLogger(__name__)


class PlanificationService:
    def __init__(self, osrm: OsrmClient | None, llm: LlmClient | None) -> None:
        self._osrm = osrm
        self._llm = llm

    def proposer(self, requete: PlanificationRequest) -> PlanificationResponse:
        if not requete.dossiers:
            return PlanificationResponse(comparaison="Aucun dossier à planifier sur la période.")
        sites_utiles = {d.chargement.site_id for d in requete.dossiers} | {
            d.dechargement.site_id for d in requete.dossiers
        }
        points = {s.id: (s.latitude, s.longitude) for s in requete.sites if s.id in sites_utiles}
        matrice = construire_matrice(self._osrm, points)
        solveur = Solveur(requete, matrice)
        propositions, non_planifiables = solveur.propositions()
        retenues = selectionner(propositions, requete.nb_options)
        options = [self._option(rang, r, solveur) for rang, r in enumerate(retenues, start=1)]

        redaction = rediger(self._llm, options)
        for option in options:
            option.justification = redaction.justifications.get(option.rang, "")
            option.recommandee = option.rang == redaction.recommandation
        logger.info(
            "Planification : %d proposition(s) calculée(s), %d option(s) retenue(s), "
            "distances %s, rédaction %s",
            len(propositions),
            len(options),
            matrice.source,
            redaction.source,
        )
        return PlanificationResponse(
            options=options,
            comparaison=redaction.comparaison if options else "Aucune option réalisable.",
            dossiers_non_planifiables=non_planifiables,
            source_distances=matrice.source,
            source_redaction=redaction.source,
        )

    @staticmethod
    def _option(rang: int, retenue: OptionRetenue, solveur: Solveur) -> OptionVoyage:
        p = retenue.proposition
        par_id = {d.id: d for d in p.dossiers}
        charge = 0.0
        arrets = []
        for ordre, a in enumerate(p.tournee.arrets):
            charge += sum(par_id[i].poids_brut_kg for i in a.charges)
            charge -= sum(par_id[i].poids_brut_kg for i in a.decharges)
            site = solveur.sites[a.site_id]
            arrets.append(
                ArretPropose(
                    ordre=ordre,
                    site_id=a.site_id,
                    libelle=site.libelle,
                    latitude=site.latitude,
                    longitude=site.longitude,
                    dossiers_charges=a.charges,
                    dossiers_decharges=a.decharges,
                    eta=a.eta,
                    etd=a.etd,
                    distance_depuis_precedent_km=round(a.distance_km, 1),
                    duree_depuis_precedent_min=round(a.duree_min),
                    charge_apres_kg=round(max(charge, 0.0), 1),
                    attente_min=round(a.attente_min),
                    fenetre_respectee=a.fenetre_respectee,
                )
            )
        poids = p.poids_kg
        return OptionVoyage(
            rang=rang,
            objectif=retenue.objectif,
            libelle_objectif=retenue.libelle_objectif,
            type_voyage="SIMPLE" if len(p.dossiers) == 1 else solveur.requete.type_voyage,
            dossier_ids=[d.id for d in p.dossiers],
            arrets=arrets,
            vehicule_id=p.support.vehicule.id,
            remorque_id=p.support.remorque.id if p.support.remorque else None,
            chauffeur_ids=[c.id for c in p.chauffeurs],
            depart_prevu=p.tournee.depart,
            arrivee_prevue=p.tournee.arrivee,
            indicateurs=Indicateurs(
                nb_dossiers=len(p.dossiers),
                distance_km=round(p.tournee.distance_km, 1),
                duree_conduite_min=round(p.tournee.conduite_min),
                duree_totale_min=round(p.tournee.duree_totale_min),
                poids_kg=poids,
                volume_m3=round(sum(d.volume_m3 for d in p.dossiers), 2),
                palettes=sum(d.nb_palettes for d in p.dossiers),
                taux_remplissage_poids=round(p.taux_poids, 3),
                taux_remplissage_volume=round(p.taux_volume, 3),
                fenetres_manquees=p.tournee.fenetres_manquees,
                cout_estime=round(p.cout, 2),
                cout_par_tonne=round(p.cout_par_tonne, 2) if poids else None,
            ),
            alertes=list(p.alertes),
        )
