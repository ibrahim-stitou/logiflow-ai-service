import os
import random
import logging

logger = logging.getLogger(__name__)

# URL du backend (à configurer)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

def calculer_score_sante(vehicule_id: str):
    """
    Calcule un score de santé pour un véhicule.
    
    Args:
        vehicule_id: Identifiant du véhicule
    
    Returns:
        dict: {"score": int, "statut": str, "recommandation": str}
    """
    try:
        # TODO: Appeler le backend pour récupérer les données réelles
        # Pour l'instant, simulation
        
        # Score entre 0 et 100
        score = random.randint(60, 95)
        
        if score >= 80:
            statut = "BON"
            recommandation = "Aucune maintenance urgente requise."
        elif score >= 60:
            statut = "SURVEILLER"
            recommandation = "Maintenance à planifier dans les 30 prochains jours."
        else:
            statut = "URGENT"
            recommandation = "Maintenance immédiate requise !"
        
        return {
            "score": score,
            "statut": statut,
            "recommandation": recommandation
        }
        
    except Exception as e:
        logger.error(f"Erreur maintenance: {e}")
        return {"error": str(e)}