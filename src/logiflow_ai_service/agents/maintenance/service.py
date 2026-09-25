"""Agent de maintenance prédictive : analyse déterministe + synthèse rédigée par le LLM.

Comme pour la planification, le LLM ne calcule rien : il explique en une phrase la situation des
engins (véhicules et remorques) les plus à risque et rédige une synthèse de flotte. Gabarit de
repli s'il est indisponible.
"""

import json
import logging
import re

from logiflow_ai_service.agents.maintenance.analyse import analyser
from logiflow_ai_service.agents.maintenance.schemas import (
    AnalyseVehicule,
    MaintenanceRequest,
    MaintenanceResponse,
)
from logiflow_ai_service.infrastructure.exceptions import LlmQuotaError, UpstreamServiceError
from logiflow_ai_service.infrastructure.llm_client import LlmClient

logger = logging.getLogger(__name__)

NB_VEHICULES_COMMENTES = 8

PROMPT_SYSTEME = """Tu es l'assistant maintenance d'un transporteur routier (TMS LogiFlow).
On te donne l'analyse déjà calculée des engins les plus à risque, véhicules ou remorques (score de
santé sur 100, échéances, anomalies dont les sinistres, actions recommandées).
Tu ne modifies aucun chiffre et n'inventes rien.
Réponds UNIQUEMENT par un objet JSON, en français :
{"explications": {"<immatriculation>": "<1 phrase : le risque principal et l'action à mener>"},
 "synthese": "<3 à 4 phrases : état de la flotte, priorités de la semaine, points d'attention>"}"""


def _resume(a: AnalyseVehicule) -> dict:
    return {
        "immatriculation": a.immatriculation,
        "engin": "remorque" if a.type_engin == "REMORQUE" else "véhicule",
        "score": a.score,
        "statut": a.statut,
        "kmParJour": a.km_par_jour,
        "kmAvantEcheance": a.km_avant_echeance,
        "echeance": a.date_echeance.isoformat() if a.date_echeance else None,
        "anomalies": a.anomalies,
        "actions": [f"{r.priorite} : {r.libelle}" for r in a.recommandations[:3]],
    }


def _explication_gabarit(a: AnalyseVehicule) -> str:
    if not a.recommandations and not a.anomalies:
        return "Aucune échéance ni anomalie sur l'horizon analysé."
    premiere = a.recommandations[0] if a.recommandations else None
    texte = f"Score {round(a.score)}/100"
    if premiere:
        texte += f" : {premiere.libelle.lower()} ({premiere.priorite.lower()})"
        if premiere.avant_le:
            texte += f" avant le {premiere.avant_le.strftime('%d/%m/%Y')}"
    if a.anomalies:
        texte += f". {a.anomalies[0]}"
    return texte + "."


def _synthese_gabarit(analyses: list[AnalyseVehicule]) -> str:
    par_statut: dict[str, int] = {}
    for a in analyses:
        par_statut[a.statut] = par_statut.get(a.statut, 0) + 1
    urgentes = sum(
        1
        for a in analyses
        for r in a.recommandations
        if r.priorite == "URGENTE" and not r.deja_planifie
    )
    return (
        f"{len(analyses)} engin(s) analysé(s) : {par_statut.get('CRITIQUE', 0)} critique(s), "
        f"{par_statut.get('A_PLANIFIER', 0)} à planifier, {par_statut.get('SURVEILLER', 0)} à "
        f"surveiller, {par_statut.get('BON', 0)} en bon état. {urgentes} action(s) urgente(s) "
        "restent à planifier."
    )


class MaintenanceService:
    def __init__(self, llm: LlmClient | None) -> None:
        self._llm = llm

    def recommander(self, requete: MaintenanceRequest) -> MaintenanceResponse:
        analyses = analyser(requete)
        for a in analyses:
            a.explication = _explication_gabarit(a)
        synthese = _synthese_gabarit(analyses)
        source = "GABARIT"

        a_commenter = [a for a in analyses if a.statut != "BON"][:NB_VEHICULES_COMMENTES]
        if self._llm is not None and a_commenter:
            try:
                brut = self._llm.chat(
                    PROMPT_SYSTEME,
                    json.dumps(
                        {"vehicules": [_resume(a) for a in a_commenter], "synthese": synthese},
                        ensure_ascii=False,
                    ),
                )
                donnees = json.loads(re.search(r"\{.*\}", brut, re.DOTALL).group(0))
                explications = donnees.get("explications") or {}
                for a in a_commenter:
                    texte = str(explications.get(a.immatriculation) or "").strip()
                    if texte:
                        a.explication = texte
                synthese = str(donnees.get("synthese") or "").strip() or synthese
                source = "LLM"
            except (
                UpstreamServiceError,
                LlmQuotaError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                logger.info("Rédaction LLM indisponible, repli par gabarit : %s", exc)

        logger.info("Maintenance : %d engin(s) analysé(s), rédaction %s", len(analyses), source)
        return MaintenanceResponse(vehicules=analyses, synthese=synthese, source_redaction=source)
