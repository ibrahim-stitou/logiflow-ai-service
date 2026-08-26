import os
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Seuils de maintenance
SEUIL_KILOMETRAGE_VIDANGE = 15000
SEUIL_KILOMETRAGE_FREINS = 30000
SEUIL_KILOMETRAGE_PNEUS = 40000
SEUIL_JOURS_VISITE_TECHNIQUE = 365
SEUIL_PANNES_MAX = 3
SEUIL_AGE_MAX = 10


def calculer_score_sante(vehicule):
    """
    Calcule un score de santé pour un véhicule.
    
    Args:
        vehicule: dict avec les infos du véhicule
    
    Returns:
        dict: {"score": int, "statut": str, "recommandations": list}
    """
    score = 100
    recommandations = []
    
    # 1. Vidange
    km_vidange = vehicule.get("kmDepuisVidange", 0)
    if km_vidange > SEUIL_KILOMETRAGE_VIDANGE:
        score -= 20
        recommandations.append({
            "type": "VIDANGE",
            "urgence": "ELEVEE",
            "message": f"Vidange recommandée (dernière vidange à {km_vidange} km)"
        })
    
    # 2. Freins
    km_freins = vehicule.get("kmDepuisFreins", 0)
    if km_freins > SEUIL_KILOMETRAGE_FREINS:
        score -= 15
        recommandations.append({
            "type": "FREINS",
            "urgence": "ELEVEE",
            "message": f"Contrôle des freins recommandé ({km_freins} km)"
        })
    
    # 3. Pneus
    km_pneus = vehicule.get("kmDepuisPneus", 0)
    if km_pneus > SEUIL_KILOMETRAGE_PNEUS:
        score -= 10
        recommandations.append({
            "type": "PNEUS",
            "urgence": "MOYENNE",
            "message": f"Vérification des pneus recommandée ({km_pneus} km)"
        })
    
    # 4. Visite technique
    date_visite = vehicule.get("dateVisiteTechnique")
    if date_visite:
        try:
            d_visite = datetime.fromisoformat(date_visite)
            jours = (datetime.now() - d_visite).days
            if jours > SEUIL_JOURS_VISITE_TECHNIQUE:
                score -= 25
                recommandations.append({
                    "type": "VISITE_TECHNIQUE",
                    "urgence": "CRITIQUE",
                    "message": f"Visite technique obligatoire (dernière visite il y a {jours} jours)"
                })
        except:
            pass
    
    # 5. Âge du véhicule
    age = vehicule.get("ageAns", 0)
    if age > SEUIL_AGE_MAX:
        score -= 10
        recommandations.append({
            "type": "USURE",
            "urgence": "MOYENNE",
            "message": f"Véhicule ancien ({age} ans), surveillance accrue"
        })
    
    # 6. Pannes récentes
    nb_pannes = vehicule.get("nbPannes", 0)
    if nb_pannes > SEUIL_PANNES_MAX:
        score -= 10
        recommandations.append({
            "type": "ANOMALIE",
            "urgence": "ELEVEE",
            "message": f"{nb_pannes} pannes récentes, inspection recommandée"
        })
    
    score = max(0, min(100, score))
    
    if score >= 80:
        statut = "BON"
    elif score >= 60:
        statut = "SURVEILLER"
    elif score >= 40:
        statut = "A_PLANIFIER"
    else:
        statut = "CRITIQUE"
    
    return {
        "score": score,
        "statut": statut,
        "recommandations": recommandations,
        "prochaineMaintenance": proposer_date_maintenance(score)
    }


def proposer_date_maintenance(score):
    """Propose une date pour la prochaine maintenance."""
    if score >= 80:
        delai = 30
    elif score >= 60:
        delai = 15
    elif score >= 40:
        delai = 7
    else:
        delai = 1
    
    return (datetime.now() + timedelta(days=delai)).isoformat()