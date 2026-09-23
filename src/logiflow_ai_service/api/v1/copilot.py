"""Routes du copilote — voir docs/integration-ia.md côté backend.

- POST /copilot/ask : ancienne question/réponse unique (conservée pendant la migration du front).
- /copilot/conversations/** : chatbot persistant. L'utilisateur est identifié par l'en-tête
  `X-Utilisateur-Id`, posé par Spring (seul appelant, authentifié par la clé interne) après
  validation du JWT ; toute conversation d'un autre utilisateur répond 404.
- POST /copilot/conversations/<id>/messages : réponse streamée en `text/event-stream`.
"""

import logging
from uuid import UUID

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from pydantic import BaseModel, ValidationError

from logiflow_ai_service.agents.copilot.outils import ContexteAppel
from logiflow_ai_service.agents.copilot.schemas import (
    ConversationDetailDto,
    ConversationDto,
    CopilotAskRequest,
    CreerConversationRequest,
    EnvoyerMessageRequest,
    FeedbackRequest,
    MessageDto,
    RenommerConversationRequest,
)
from logiflow_ai_service.agents.copilot.service import ConversationIntrouvable, ConversationService
from logiflow_ai_service.agents.copilot.sse import evenement_sse
from logiflow_ai_service.errors import validation_problem
from logiflow_ai_service.infrastructure.exceptions import UpstreamServiceError
from logiflow_ai_service.security import require_internal_api_key

logger = logging.getLogger(__name__)

bp = Blueprint("copilot", __name__, url_prefix="/copilot")

HEADER_UTILISATEUR = "X-Utilisateur-Id"
_LIMITE_MAX = 100


class RequeteInvalide(Exception):
    def __init__(self, corps: dict) -> None:
        self.corps = corps


@bp.errorhandler(RequeteInvalide)
def _requete_invalide(exc: RequeteInvalide):
    return jsonify(exc.corps), 400


@bp.errorhandler(ConversationIntrouvable)
def _introuvable(_exc: ConversationIntrouvable):
    return jsonify({"title": "Conversation introuvable", "status": 404}), 404


def _conversations() -> ConversationService:
    return current_app.config["CONVERSATION_SERVICE"]


def _corps[T: BaseModel](schema: type[T]) -> T:
    try:
        return schema.model_validate(request.get_json(force=True, silent=True) or {})
    except ValidationError as exc:
        raise RequeteInvalide(validation_problem(exc)) from exc


def _utilisateur_id() -> str:
    utilisateur_id = (request.headers.get(HEADER_UTILISATEUR) or "").strip()
    if not utilisateur_id:
        raise RequeteInvalide(
            {
                "title": "Requête invalide",
                "status": 400,
                "detail": f"L'en-tête {HEADER_UTILISATEUR} est requis.",
            }
        )
    return utilisateur_id


def _entier(nom: str, defaut: int, maximum: int) -> int:
    try:
        valeur = int(request.args.get(nom, defaut))
    except ValueError:
        valeur = defaut
    return max(0, min(valeur, maximum))


@bp.post("/ask")
@require_internal_api_key
def ask():
    try:
        payload = CopilotAskRequest.model_validate(request.get_json(force=True, silent=False))
    except ValidationError as exc:
        return jsonify(validation_problem(exc)), 400

    try:
        reponse = current_app.config["COPILOTE_SERVICE"].repondre(payload)
    except UpstreamServiceError:
        logger.warning("Agent copilote indisponible (Ollama injoignable)", exc_info=True)
        return jsonify({"title": "Service IA indisponible", "status": 503}), 503

    return jsonify(reponse.model_dump(by_alias=True)), 200


@bp.get("/conversations")
@require_internal_api_key
def lister_conversations():
    conversations = _conversations().lister(
        _utilisateur_id(), _entier("limite", 30, _LIMITE_MAX), _entier("decalage", 0, 10_000)
    )
    return jsonify(
        [ConversationDto.depuis(c).model_dump(mode="json", by_alias=True) for c in conversations]
    )


@bp.post("/conversations")
@require_internal_api_key
def creer_conversation():
    utilisateur_id = _utilisateur_id()
    corps = _corps(CreerConversationRequest)
    conversation = _conversations().creer(utilisateur_id, corps.titre)
    return jsonify(ConversationDto.depuis(conversation).model_dump(mode="json", by_alias=True)), 201


@bp.get("/conversations/<uuid:conversation_id>")
@require_internal_api_key
def obtenir_conversation(conversation_id: UUID):
    utilisateur_id = _utilisateur_id()
    service = _conversations()
    conversation = service.obtenir(conversation_id, utilisateur_id)
    detail = ConversationDetailDto(
        **ConversationDto.depuis(conversation).model_dump(),
        messages=[MessageDto.depuis(m) for m in service.messages(conversation_id, utilisateur_id)],
    )
    return jsonify(detail.model_dump(mode="json", by_alias=True))


@bp.patch("/conversations/<uuid:conversation_id>")
@require_internal_api_key
def renommer_conversation(conversation_id: UUID):
    utilisateur_id = _utilisateur_id()
    corps = _corps(RenommerConversationRequest)
    conversation = _conversations().renommer(conversation_id, utilisateur_id, corps.titre)
    return jsonify(ConversationDto.depuis(conversation).model_dump(mode="json", by_alias=True))


@bp.delete("/conversations/<uuid:conversation_id>")
@require_internal_api_key
def supprimer_conversation(conversation_id: UUID):
    _conversations().supprimer(conversation_id, _utilisateur_id())
    return "", 204


@bp.post("/messages/<uuid:message_id>/feedback")
@require_internal_api_key
def noter_message(message_id: UUID):
    utilisateur_id = _utilisateur_id()
    corps = _corps(FeedbackRequest)
    _conversations().noter(message_id, utilisateur_id, corps.note, corps.commentaire)
    return "", 204


@bp.post("/conversations/<uuid:conversation_id>/messages")
@require_internal_api_key
def envoyer_message(conversation_id: UUID):
    corps = _corps(EnvoyerMessageRequest)
    contexte = ContexteAppel(
        jeton=corps.contexte,
        utilisateur_id=corps.utilisateur.id,
        nom=corps.utilisateur.nom or corps.utilisateur.id,
        roles=corps.utilisateur.roles,
        correlation_id=corps.correlation_id,
    )
    # Lève ConversationIntrouvable (404) AVANT l'envoi des en-têtes du flux.
    evenements = _conversations().envoyer(conversation_id, corps.question, contexte)

    def flux():
        for nom, donnees in evenements:
            yield evenement_sse(nom, donnees)

    return Response(
        stream_with_context(flux()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
