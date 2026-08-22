from flask import Blueprint, request, jsonify
from logiflow_ai_service.services.osrm import calculer_itineraire

itinerary_bp = Blueprint("itinerary", __name__, url_prefix="/internal/ai/v1/itinerary")

@itinerary_bp.route("/calculer", methods=["POST"])
def calculer():
    """Calcule la distance et la durée entre deux points."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Body JSON attendu"}), 400
    
    # Vérifier les champs obligatoires
    required = ["origineLat", "origineLon", "destinationLat", "destinationLon"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Champ manquant: {field}"}), 400
    
    resultat = calculer_itineraire(
        data["origineLat"],
        data["origineLon"],
        data["destinationLat"],
        data["destinationLon"]
    )
    
    if "error" in resultat:
        return jsonify(resultat), 500
    
    return jsonify(resultat)