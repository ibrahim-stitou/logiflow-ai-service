"""POST /internal/ai/v1/maintenance/recommander — contrat documenté, non implémenté.

Voir docs/integration-ia.md côté backend, section "Agent de maintenance prédictive" : reprendra
le même schéma que les autres agents une fois le besoin précisé (données `ScoreSante` et
historique `OrdreTravail` transmises par Spring Boot). En attendant, renvoie 501 explicitement
plutôt que 404, pour distinguer "route pas encore implémentée" de "route inexistante".
"""

from flask import Blueprint, jsonify

from logiflow_ai_service.security import require_internal_api_key

bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")


@bp.post("/recommander")
@require_internal_api_key
def recommander():
    return (
        jsonify(
            {
                "title": "Agent de maintenance prédictive non implémenté",
                "status": 501,
                "detail": "Contrat documenté dans docs/integration-ia.md, en attente de "
                "spécification du besoin métier.",
            }
        ),
        501,
    )
