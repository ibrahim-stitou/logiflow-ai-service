from flask import Flask, request, jsonify
import os
from logiflow_ai_service.services.database import init_db
from logiflow_ai_service.routes.copilot import copilot_bp
from logiflow_ai_service.routes.itinerary import itinerary_bp
from logiflow_ai_service.routes.groupage import groupage_bp
from logiflow_ai_service.routes.maintenance import maintenance_bp
from logiflow_ai_service.audit.logger import log_erreur
from logiflow_ai_service.routes.chauffeur import chauffeur_bp

API_KEY = os.getenv("INTERNAL_API_KEY", "logiflow-ai-secret-2026")

def create_app():
    app = Flask(__name__)

    # Initialiser la base de données IA
    init_db(app)
    
    @app.route('/health')
    def health():
        return {"status": "UP"}
    
    # Middleware pour valider la clé API
    @app.before_request
    def valider_cle_api():
        if request.endpoint == 'health':
            return  # Ne pas bloquer /health
        
        api_key = request.headers.get('X-Internal-Api-Key')
        if not api_key or api_key != API_KEY:
            log_erreur(request.endpoint or "unknown", "Clé API invalide")
            return jsonify({"error": "Clé API invalide"}), 401
    
    # Enregistrer les routes
    app.register_blueprint(copilot_bp)
    app.register_blueprint(itinerary_bp)
    app.register_blueprint(groupage_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(chauffeur_bp)
    
    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)