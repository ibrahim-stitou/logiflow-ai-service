"""Vérification de la clé API interne (service-à-service).

Ce n'est PAS une authentification utilisateur : le JWT Keycloak s'arrête au backend Spring Boot,
seul appelant légitime de cette API — voir docs/integration-ia.md côté backend
(logiflow-backend). Entre Spring Boot et Flask, l'authentification est un secret partagé de
service à service, transporté par l'en-tête X-Internal-Api-Key.
"""

from collections.abc import Callable
from functools import wraps

from flask import current_app, jsonify, request

API_KEY_HEADER = "X-Internal-Api-Key"


def require_internal_api_key(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = current_app.config["SETTINGS"].internal_api_key
        provided = request.headers.get(API_KEY_HEADER)
        if not provided or provided != expected:
            return (
                jsonify(
                    {
                        "title": "Clé API interne manquante ou invalide",
                        "status": 401,
                        "detail": f"L'en-tête {API_KEY_HEADER} est requis et doit être valide.",
                    }
                ),
                401,
            )
        return view(*args, **kwargs)

    return wrapper
