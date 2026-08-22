from flask import Blueprint, request, jsonify
from logiflow_ai_service.services.ollama import call_ollama
from logiflow_ai_service.audit.logger import log_ia_interaction, log_erreur
import time

copilot_bp = Blueprint("copilot", __name__, url_prefix="/internal/ai/v1/copilot")

@copilot_bp.route("/ask", methods=["POST"])
def ask():
    """Endpoint du copilote conversationnel."""
    data = request.get_json()
    
    if not data or "question" not in data:
        return jsonify({"error": "Question manquante"}), 400
    
    user_id = request.headers.get("X-User-Id", "anonymous")
    question = data["question"]
    
    debut = time.time()
    
    try:
        reponse = call_ollama(question)
        duree = int((time.time() - debut) * 1000)
        log_ia_interaction(user_id, "copilot/ask", question, reponse, True, duree)
        return jsonify({"reponse": reponse, "modele": "llama3.1"})
    except Exception as e:
        log_erreur("copilot/ask", str(e), user_id)
        return jsonify({"error": "Erreur interne"}), 500