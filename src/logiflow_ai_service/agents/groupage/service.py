"""Agent de groupage : propose des regroupements de dossiers de transport compatibles.

Heuristique de remplissage de capacité (poids/volume/ADR), faute de données de géolocalisation
des sites transmises dans le contrat actuel (voir "Limite assumée" dans docs/integration-ia.md
côté backend) : ne modélise pas la proximité géographique des points de chargement/déchargement.
`gainKm`/`gainMarge` restent donc toujours `null` — un vrai calcul de gain nécessiterait de croiser
l'agent itinéraire (OSRM) avec les itinéraires groupés vs. séparés, prévu dans un lot ultérieur une
fois `dossier.api.DossierSummary` enrichi avec les identifiants de site.
"""

from itertools import combinations

from logiflow_ai_service.agents.groupage.schemas import (
    DossierCandidat,
    GroupageAnalyserRequest,
    GroupageAnalyserResponse,
    PropositionGroupage,
)

# Capacité d'un semi-remorque standard — approximation faute de données réelles de véhicule
# assigné à ce stade du processus (l'affectation véhicule intervient après le groupage).
_CAPACITE_POIDS_KG = 24_000.0
_CAPACITE_VOLUME_M3 = 90.0
_CAPACITE_PALETTES = 33

_CONFIANCE_HEURISTIQUE = 0.6
_SEUIL_REMPLISSAGE_MIN = 0.3  # en dessous, le groupage n'apporte pas assez de valeur


class GroupageService:
    def analyser(self, request: GroupageAnalyserRequest) -> GroupageAnalyserResponse:
        propositions = [
            proposition
            for a, b in combinations(request.dossiers, 2)
            if (proposition := self._evaluer_paire(a, b)) is not None
        ]
        propositions.sort(key=lambda p: p.score, reverse=True)
        return GroupageAnalyserResponse(propositions=propositions)

    def _evaluer_paire(self, a: DossierCandidat, b: DossierCandidat) -> PropositionGroupage | None:
        if a.contient_adr != b.contient_adr:
            # ADR et non-ADR ne se mélangent pas (contrainte réglementaire simplifiée).
            return None

        poids_total = a.poids_brut_kg + b.poids_brut_kg
        volume_total = a.volume_m3 + b.volume_m3
        palettes_total = a.nb_palettes + b.nb_palettes

        if (
            poids_total > _CAPACITE_POIDS_KG
            or volume_total > _CAPACITE_VOLUME_M3
            or palettes_total > _CAPACITE_PALETTES
        ):
            return None

        score = round(max(poids_total / _CAPACITE_POIDS_KG, volume_total / _CAPACITE_VOLUME_M3), 2)
        if score < _SEUIL_REMPLISSAGE_MIN:
            return None

        return PropositionGroupage(
            dossier_ids=[a.id, b.id],
            score=score,
            confiance=_CONFIANCE_HEURISTIQUE,
            gain_km=None,
            gain_marge=None,
            justification=(
                f"Remplissage estimé {score:.0%} "
                f"(poids {poids_total:.0f}/{_CAPACITE_POIDS_KG:.0f} kg, "
                f"volume {volume_total:.1f}/{_CAPACITE_VOLUME_M3:.0f} m³), même statut ADR. "
                "Proximité géographique non évaluée (données de site non transmises)."
            ),
        )
