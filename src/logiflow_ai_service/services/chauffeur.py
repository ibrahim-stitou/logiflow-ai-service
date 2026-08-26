import os
import logging

logger = logging.getLogger(__name__)


def selectionner_chauffeur(chauffeurs, voyage):
    """
    Sélectionne le chauffeur le plus adapté pour un voyage.
    
    Args:
        chauffeurs: list de dict avec les infos des chauffeurs
        voyage: dict avec les infos du voyage
    
    Returns:
        dict: Le chauffeur sélectionné
    """
    chauffeurs_disponibles = []
    
    for c in chauffeurs:
        # 1. Vérifier le permis
        if not verifier_permis(c, voyage):
            continue
        
        # 2. Vérifier les autorisations
        if not verifier_autorisations(c, voyage):
            continue
        
        # 3. Vérifier la disponibilité
        if not verifier_disponibilite(c, voyage):
            continue
        
        # 4. Vérifier le temps de conduite
        if not verifier_temps_conduite(c, voyage):
            continue
        
        # 5. Vérifier les habilitations (ADR, etc.)
        if not verifier_habilitations(c, voyage):
            continue
        
        # 6. Calculer un score
        score = calculer_score_chauffeur(c, voyage)
        c["score"] = score
        chauffeurs_disponibles.append(c)
    
    # Trier par score décroissant
    chauffeurs_disponibles.sort(key=lambda x: x["score"], reverse=True)
    
    return chauffeurs_disponibles[0] if chauffeurs_disponibles else None


def verifier_permis(chauffeur, voyage):
    """Vérifie que le chauffeur a le bon permis."""
    permis_requis = voyage.get("permisRequis", "CE")
    permis_chauffeur = chauffeur.get("permis", "")
    return permis_requis in permis_chauffeur


def verifier_autorisations(chauffeur, voyage):
    """Vérifie les autorisations de circulation."""
    if voyage.get("international", False):
        return chauffeur.get("autorisationEurope", False)
    return True


def verifier_disponibilite(chauffeur, voyage):
    """Vérifie que le chauffeur est disponible."""
    # Vérifier qu'il n'a pas d'autre voyage planifié sur cette période
    voyages_planifies = chauffeur.get("voyagesPlanifies", [])
    debut = voyage.get("dateDebut")
    fin = voyage.get("dateFin")
    
    for v in voyages_planifies:
        if not (v["fin"] < debut or v["debut"] > fin):
            return False
    return True


def verifier_temps_conduite(chauffeur, voyage):
    """Vérifie le solde de temps de conduite."""
    solde = chauffeur.get("soldeTempsConduite", 0)  # en minutes
    duree_voyage = voyage.get("dureeMin", 0)
    return solde >= duree_voyage


def verifier_habilitations(chauffeur, voyage):
    """Vérifie les habilitations (ADR, etc.)."""
    if voyage.get("contientAdr", False):
        return chauffeur.get("habilitationAdr", False)
    return True


def calculer_score_chauffeur(chauffeur, voyage):
    """Calcule un score pour le chauffeur."""
    score = 100
    
    # Bonus pour l'expérience
    experience = chauffeur.get("experienceAnnees", 0)
    if experience > 10:
        score += 10
    elif experience > 5:
        score += 5
    
    # Bonus pour la connaissance de la région
    if chauffeur.get("connaitRegion", False):
        score += 5
    
    # Bonus pour les habilitations supplémentaires
    if chauffeur.get("habilitationAdr", False):
        score += 5
    
    return min(100, score)