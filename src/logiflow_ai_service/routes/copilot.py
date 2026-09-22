from flask import Blueprint, request, jsonify
from logiflow_ai_service.services.ollama import call_ollama
from logiflow_ai_service.services.intent_detector import detecter_intention
from logiflow_ai_service.services.tools import (
    get_vehicules_disponibles,
    get_dossier_details,
    get_chauffeur_details
)
from logiflow_ai_service.services.database import sauvegarder_chat, sauvegarder_requete
from logiflow_ai_service.audit.logger import log_ia_interaction, log_erreur
import time

copilot_bp = Blueprint("copilot", __name__, url_prefix="/internal/ai/v1/copilot")

@copilot_bp.route("/ask", methods=["POST"])
def ask():
    """Chatbot intelligent qui détecte l'intention et appelle les tools."""
    data = request.get_json()
    
    if not data or "question" not in data:
        return jsonify({"error": "Question manquante"}), 400
    
    user_id = request.headers.get("X-User-Id", "anonymous")
    question = data["question"]
    
    debut = time.time()
    
    # 1. Détecter l'intention
    intention, params = detecter_intention(question)
    print(f"🎯 Intention: {intention}, Params: {params}")
    
    # 2. Appeler le bon tool
    resultat = None
    try:
        if intention == "vehicules_disponibles":
            resultat = get_vehicules_disponibles(params.get("date", "demain"))
        elif intention == "dossier":
            resultat = get_dossier_details(params.get("dossier_id"))
        elif intention == "chauffeur":
            resultat = get_chauffeur_details(params.get("chauffeur_id", "C1"))
        
        # 3. Formater la réponse avec Ollama
        if resultat:
            prompt = f"""
            L'utilisateur a demandé : {question}
            Voici les données récupérées : {resultat}
            
            Formule une réponse claire et professionnelle en français.
            N'invente aucun chiffre, utilise strictement les données fournies.
            Ne signe pas ta réponse, ne mets pas de formule de politesse finale.
            Réponds directement à la question.
            """
            reponse = call_ollama(prompt)
        else:
            reponse = call_ollama(question)
        
        duree = int((time.time() - debut) * 1000)
        
        # 4. Journalisation (audit fichier)
        log_ia_interaction(user_id, "copilot/ask", question, reponse, True, duree)
        
        # 5. Sauvegarde dans la base de données IA (PostgreSQL)
        sauvegarder_chat(user_id, question, reponse, intention)
        sauvegarder_requete(user_id, "copilot/ask", question, True, duree)
        
        return jsonify({
            "reponse": reponse,
            "intention": intention,
            "modele": "llama3.2"
        })
        
    except Exception as e:
        duree = int((time.time() - debut) * 1000)
        
        # Journalisation de l'erreur
        log_erreur("copilot/ask", str(e), user_id)
        
        # Sauvegarde de l'échec dans la base IA
        sauvegarder_requete(user_id, "copilot/ask", question, False, duree)
        
        return jsonify({"error": f"Erreur: {str(e)}"}), 500