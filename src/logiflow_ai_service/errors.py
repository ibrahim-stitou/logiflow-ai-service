"""Gestionnaires d'erreurs génériques : réponses JSON uniformes, jamais de stack trace exposée."""

import logging

from flask import Flask, jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def validation_problem(exc: ValidationError) -> dict:
    """Représentation JSON-sérialisable d'une ValidationError Pydantic.

    `exc.errors()` inclut parfois l'exception Python d'origine dans `ctx` (validateurs
    personnalisés) : non sérialisable telle quelle par le JSONProvider de Flask, d'où cette
    projection explicite vers des champs garantis sérialisables.
    """
    return {
        "title": "Requête invalide",
        "status": 400,
        "errors": [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ],
    }


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):
        return jsonify({"title": exc.name, "status": exc.code, "detail": exc.description}), (
            exc.code or 500
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(exc: Exception):
        logger.exception("Erreur interne non gérée")
        return jsonify({"title": "Erreur interne", "status": 500}), 500
