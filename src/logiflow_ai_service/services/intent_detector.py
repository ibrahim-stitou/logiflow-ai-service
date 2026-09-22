"""
Détecte l'intention de l'utilisateur à partir de sa question.
Permet de router la question vers le bon agent ou le bon tool.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Expression régulière pour capturer les références de dossiers (ex: DT-2026-001, DT-001)
REGEX_DOSSIER = r'DT[- ]?\d{4}[- ]?\d{3}|DT[- ]?\d{3}'


def detecter_intention(question: str):
    """
    Détecte l'intention de l'utilisateur.
    
    Args:
        question: La question posée par l'utilisateur
    
    Returns:
        tuple: (intention, params)
    """
    question_lower = question.lower()
    
    # 1. Groupage (AVANT dossier, car "grouper DT-001" contient "DT-")
    if any(mot in question_lower for mot in ["grouper", "groupage", "regrouper", "combiner"]):
        dossiers = re.findall(REGEX_DOSSIER, question, re.IGNORECASE)
        return ("groupage", {"dossiers": dossiers})
    
    # 2. Véhicules disponibles
    if any(mot in question_lower for mot in ["camion", "véhicule", "vehicule", "truck", "poids lourd"]):
        if any(mot in question_lower for mot in ["disponible", "libre", "dispo", "libérer"]):
            date = extraire_date(question_lower)
            return ("vehicules_disponibles", {"date": date})
    
    # 3. Dossier de transport
    if "dossier" in question_lower or "dt-" in question_lower or "dt " in question_lower:
        dossiers = re.findall(REGEX_DOSSIER, question, re.IGNORECASE)
        if dossiers:
            return ("dossier", {"dossier_id": dossiers[0].upper().replace(" ", "-")})
        return ("dossier", {"question": question})
    
    # 4. Chauffeur
    if any(mot in question_lower for mot in ["chauffeur", "conducteur", "driver"]):
        return ("chauffeur", {"question": question})
    
    # 5. Itinéraire
    if any(mot in question_lower for mot in ["km", "distance", "trajet", "itinéraire", "itineraire", "route"]):
        return ("itineraire", {"question": question})
    
    # 6. Maintenance
    if any(mot in question_lower for mot in ["maintenance", "vidange", "révision", "revision", "entretien", "panne"]):
        return ("maintenance", {"question": question})
    
    # 7. Voyage
    if any(mot in question_lower for mot in ["voyage", "trajet en cours", "livraison"]):
        return ("voyage", {"question": question})
    
    # 8. Par défaut : question générale
    return ("general", {"question": question})


def extraire_date(question_lower: str) -> str:
    """
    Extrait la date de la question.
    """
    if "demain" in question_lower:
        return "demain"
    elif "aujourd'hui" in question_lower or "aujourd hui" in question_lower:
        return "aujourd'hui"
    elif "après-demain" in question_lower or "apres-demain" in question_lower:
        return "apres-demain"
    else:
        match = re.search(r'(\d{1,2})[/-](\d{1,2})', question_lower)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return "demain"