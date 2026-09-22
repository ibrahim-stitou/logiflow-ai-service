"""
Tools pour le chatbot.
Ces fonctions appellent les APIs de Spring Boot.
Pour l'instant, elles retournent des données simulées (mock).
"""

import os
import logging

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "logiflow-ai-secret-2026")

# Mode simulation (à passer à False quand les APIs seront prêtes)
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"


def get_vehicules_disponibles(date: str):
    """Récupère la liste des véhicules disponibles pour une date donnée."""
    
    if MOCK_MODE:
        logger.info(f"[MOCK] get_vehicules_disponibles(date={date})")
        return [
            {"id": "TR-042", "immatriculation": "AB-123-CD", "chargeUtileKg": 24000, "statut": "DISPONIBLE"},
            {"id": "TR-056", "immatriculation": "EF-456-GH", "chargeUtileKg": 24000, "statut": "DISPONIBLE"},
            {"id": "TR-089", "immatriculation": "IJ-789-KL", "chargeUtileKg": 24000, "statut": "DISPONIBLE"}
        ]
    
    import requests
    url = f"{BACKEND_URL}/api/v1/vehicules/disponibles"
    headers = {"X-Internal-Api-Key": INTERNAL_API_KEY}
    params = {"date": date}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Erreur {response.status_code}"}
    except Exception as e:
        logger.error(f"Erreur: {e}")
        return {"error": str(e)}


def get_dossier_details(dossier_id: str):
    """Récupère les détails d'un dossier."""
    
    if MOCK_MODE:
        logger.info(f"[MOCK] get_dossier_details(dossier_id={dossier_id})")
        return {
            "id": dossier_id,
            "reference": f"DT-{dossier_id}",
            "poidsBrutKg": 1500.5,
            "volumeM3": 12.0,
            "statut": "PLANIFIABLE",
            "contientAdr": False
        }
    
    import requests
    url = f"{BACKEND_URL}/api/v1/dossiers/{dossier_id}"
    headers = {"X-Internal-Api-Key": INTERNAL_API_KEY}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        return {"error": f"Dossier {dossier_id} introuvable"}
    except Exception as e:
        logger.error(f"Erreur: {e}")
        return {"error": str(e)}


def get_chauffeur_details(chauffeur_id: str):
    """Récupère les détails d'un chauffeur."""
    
    if MOCK_MODE:
        logger.info(f"[MOCK] get_chauffeur_details(chauffeur_id={chauffeur_id})")
        return {
            "id": chauffeur_id,
            "nom": "Jean Dupont",
            "permis": "CE",
            "habilitationAdr": True,
            "disponible": True
        }
    
    return {"error": "Non implémenté"}


def get_site_details(site_id: str):
    """Récupère les détails d'un site."""
    
    if MOCK_MODE:
        logger.info(f"[MOCK] get_site_details(site_id={site_id})")
        return {
            "id": site_id,
            "nom": "Casablanca",
            "latitude": 33.5731,
            "longitude": -7.5898
        }
    
    return {"error": "Non implémenté"}


def get_voyage_details(voyage_id: str):
    """Récupère les détails d'un voyage."""
    
    if MOCK_MODE:
        logger.info(f"[MOCK] get_voyage_details(voyage_id={voyage_id})")
        return {
            "id": voyage_id,
            "reference": "V-2026-001",
            "statut": "EN_COURS",
            "distanceTotaleKm": 350
        }
    
    return {"error": "Non implémenté"}