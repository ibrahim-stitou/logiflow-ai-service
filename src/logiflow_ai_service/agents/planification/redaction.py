"""Rédaction des justifications et de la comparaison des options.

Le LLM ne décide rien : il commente des options déjà calculées par le solveur et désigne celle
qu'il recommande parmi elles. Si le LLM est indisponible ou répond mal, un gabarit déterministe
prend le relais (recommandation = meilleur compromis remplissage / coût).
"""

import json
import logging
import re
from dataclasses import dataclass

from logiflow_ai_service.agents.planification.schemas import OptionVoyage
from logiflow_ai_service.devise import DEVISE
from logiflow_ai_service.infrastructure.exceptions import LlmQuotaError, UpstreamServiceError
from logiflow_ai_service.infrastructure.llm_client import LlmClient

logger = logging.getLogger(__name__)

PROMPT_SYSTEME = """Tu es l'assistant de planification d'un transporteur routier (TMS LogiFlow).
On te donne plusieurs propositions de voyage déjà calculées (dossiers groupés, itinéraire,
indicateurs, ressources). Tu ne modifies aucun chiffre et tu n'inventes aucune donnée.
Réponds UNIQUEMENT par un objet JSON, en français, de la forme :
{"justifications": {"<rang>": "<2 phrases max : pourquoi cette option, son point fort, sa limite>"},
 "comparaison": "<3 à 5 phrases comparant les options entre elles>",
 "recommandation": <rang de l'option recommandée>}"""


@dataclass
class Redaction:
    justifications: dict[int, str]
    comparaison: str
    recommandation: int
    source: str


def _resume(option: OptionVoyage) -> dict:
    i = option.indicateurs
    return {
        "rang": option.rang,
        "objectif": option.libelle_objectif,
        "dossiers": i.nb_dossiers,
        "distanceKm": round(i.distance_km),
        "conduiteH": round(i.duree_conduite_min / 60, 1),
        "dureeTotaleH": round(i.duree_totale_min / 60, 1),
        "remplissagePoidsPct": round(i.taux_remplissage_poids * 100),
        "remplissageVolumePct": round(i.taux_remplissage_volume * 100),
        "fenetresManquees": i.fenetres_manquees,
        "coutEstimeEur": round(i.cout_estime),
        "coutParTonneEur": round(i.cout_par_tonne) if i.cout_par_tonne else None,
        "chauffeurs": len(option.chauffeur_ids),
        "arrets": [a.libelle for a in option.arrets],
        "alertes": option.alertes,
    }


def gabarit(options: list[OptionVoyage]) -> Redaction:
    justifications = {}
    for o in options:
        i = o.indicateurs
        texte = (
            f"{o.libelle_objectif} : {i.nb_dossiers} dossier(s) sur {len(o.arrets)} arrêts, "
            f"{round(i.distance_km)} km pour un remplissage de "
            f"{round(max(i.taux_remplissage_poids, i.taux_remplissage_volume) * 100)} %."
        )
        if o.alertes:
            texte += f" Point d'attention : {o.alertes[0].lower()}."
        justifications[o.rang] = texte
    recommandee = min(
        options,
        key=lambda o: (
            o.indicateurs.fenetres_manquees,
            len(o.alertes),
            -max(o.indicateurs.taux_remplissage_poids, o.indicateurs.taux_remplissage_volume)
            + (o.indicateurs.cout_par_tonne or 0) / 1000,
        ),
    )
    lignes = [
        f"Option {o.rang} ({o.libelle_objectif.lower()}) : {o.indicateurs.nb_dossiers} dossier(s), "
        f"{round(o.indicateurs.distance_km)} km, "
        f"{round(o.indicateurs.cout_estime)} {DEVISE} estimés"
        for o in options
    ]
    comparaison = " ; ".join(lignes) + (
        f". L'option {recommandee.rang} offre le meilleur compromis entre ponctualité, "
        "remplissage et coût."
    )
    return Redaction(justifications, comparaison, recommandee.rang, "GABARIT")


def _extraire_json(texte: str) -> dict:
    correspondance = re.search(r"\{.*\}", texte, re.DOTALL)
    if not correspondance:
        raise ValueError("aucun objet JSON")
    return json.loads(correspondance.group(0))


def rediger(llm: LlmClient | None, options: list[OptionVoyage]) -> Redaction:
    repli = gabarit(options)
    if llm is None or not options:
        return repli
    try:
        brut = llm.chat(
            PROMPT_SYSTEME,
            json.dumps({"options": [_resume(o) for o in options]}, ensure_ascii=False),
        )
        donnees = _extraire_json(brut)
        rangs = {o.rang for o in options}
        justifications = {
            int(rang): str(texte).strip()
            for rang, texte in (donnees.get("justifications") or {}).items()
            if str(rang).isdigit() and int(rang) in rangs and str(texte).strip()
        }
        recommandation = int(donnees.get("recommandation", repli.recommandation))
        if recommandation not in rangs:
            recommandation = repli.recommandation
        comparaison = str(donnees.get("comparaison") or "").strip() or repli.comparaison
        return Redaction(
            {**repli.justifications, **justifications}, comparaison, recommandation, "LLM"
        )
    except (UpstreamServiceError, LlmQuotaError, ValueError, TypeError) as exc:
        logger.info("Rédaction LLM indisponible, repli par gabarit : %s", exc)
        return repli
