import os
import requests
import logging

logger = logging.getLogger(__name__)

OSRM_URL = os.getenv("OSRM_URL", "http://router.project-osrm.org/route/v1/driving")

def calculer_itineraire(lat1: float, lon1: float, lat2: float, lon2: float):
    """
    Calcule la distance et la durée entre deux points via OSRM.
    
    Args:
        lat1, lon1: Coordonnées du point de départ
        lat2, lon2: Coordonnées du point d'arrivée
    
    Returns:
        dict: {"distanceKm": float, "dureeMin": float} ou {"error": str}
    """
    try:
        url = f"{OSRM_URL}/{lon1},{lat1};{lon2},{lat2}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('code') != 'Ok':
            return {"error": "Impossible de calculer l'itinéraire"}
        
        distance_km = data['routes'][0]['distance'] / 1000
        duree_min = data['routes'][0]['duration'] / 60
        
        return {
            "distanceKm": round(distance_km, 1),
            "dureeMin": round(duree_min, 0)
        }
        
    except requests.exceptions.Timeout:
        return {"error": "Timeout OSRM"}
    except requests.exceptions.ConnectionError:
        return {"error": "Service OSRM indisponible"}
    except Exception as e:
        logger.error(f"Erreur OSRM: {e}")
        return {"error": str(e)}