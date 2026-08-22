from flask import Blueprint, request, jsonify
from logiflow_ai_service.services.ollama import call_ollama

groupage_bp = Blueprint("groupage", __name__, url_prefix="/internal/ai/v1/groupage")

@groupage_bp.route("/analyser", methods=["POST"])
def analyser_groupage():
    """
    Reçoit une liste de candidats dossiers, calcule la compatibilité,
    et retourne des propositions de groupage.
    
    Requête: {"candidats": [{"id": "...", "poidsBrutKg": ..., ...}]}
    Réponse: [{"dossierIds": ["..."], "score": 85, "gainKm": 120.5, ...}]
    """
    data = request.get_json()
    
    if not data or "candidats" not in data:
        return jsonify({"error": "Champ 'candidats' manquant"}), 400
    
    candidats = data["candidats"]
    
    if len(candidats) < 2:
        return jsonify({"error": "Au moins 2 dossiers sont nécessaires"}), 400
    
    # 1. Calculer le score de compatibilité
    score = calculer_score(candidats)
    
    # 2. Calculer le gain estimé
    gain_km = estimer_gain(candidats)
    
    # 3. Générer une justification avec Ollama
    justification = generer_justification(candidats, score, gain_km)
    
    # 4. Construire la réponse
    proposition = {
        "dossierIds": [c["id"] for c in candidats],
        "score": score,
        "confiance": 0.85,
        "gainKm": gain_km,
        "gainMarge": gain_km * 2.5,
        "justification": justification,
        "genereParIa": True
    }
    
    return jsonify([proposition])


def calculer_score(candidats):
    """Calcule un score de compatibilité entre 0 et 100."""
    score = 80
    
    # Vérifier les ADR
    adr_count = sum(1 for c in candidats if c.get("contientAdr", False))
    if 0 < adr_count < len(candidats):
        score -= 20
    
    # Vérifier le poids total
    poids_total = sum(c.get("poidsBrutKg", 0) for c in candidats)
    if poids_total > 20000:
        score -= 10
    
    # Vérifier si groupables
    if not all(c.get("groupable", True) for c in candidats):
        score -= 15
    
    return max(0, min(100, score))


def estimer_gain(candidats):
    """Estime le gain kilométrique du groupage."""
    return 50 + (len(candidats) - 1) * 30


def generer_justification(candidats, score, gain_km):
    """Génère une justification avec Ollama."""
    references = [c.get("reference", f"DT-{i}") for i, c in enumerate(candidats)]
    poids = [c.get("poidsBrutKg", 0) for c in candidats]
    
    prompt = f"""
    Tu es un expert en logistique chez LogiFlow.
    
    Analyse de groupage pour les dossiers suivants :
    - Dossiers : {', '.join(references)}
    - Poids total : {sum(poids)} kg
    - Score de compatibilité : {score}/100
    - Gain estimé : {gain_km} km
    
    Rédige une explication professionnelle de 3-4 lignes pour justifier ce groupage.
    N'invente aucun chiffre, utilise strictement les données fournies.
    """
    
    return call_ollama(prompt, temperature=0.3)