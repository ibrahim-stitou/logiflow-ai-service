"""
Module d'audit pour journaliser les interactions IA.
Utilisé pour la traçabilité et la sécurité.
"""

import logging
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# Configuration du niveau de log
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

def log_ia_interaction(
    user_id: str,
    endpoint: str,
    question: str,
    reponse: str,
    succes: bool = True,
    duree_ms: int = 0
):
    """
    Journalise une interaction IA pour l'audit.
    
    Args:
        user_id: Identifiant de l'utilisateur
        endpoint: Nom de l'endpoint appelé
        question: La question ou requête
        reponse: La réponse générée
        succes: True si l'opération a réussi
        duree_ms: Durée en millisecondes
    """
    log_entry = {
        "event": "ia_interaction",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id or "anonymous",
        "endpoint": endpoint,
        "question": question[:500] if question else None,
        "reponse": reponse[:1000] if reponse else None,
        "succes": succes,
        "duree_ms": duree_ms,
        "modele": "llama3.1"
    }
    
    if succes:
        logger.info(log_entry)
    else:
        logger.error(log_entry)


def log_erreur(endpoint: str, erreur: str, user_id: str = None):
    """
    Journalise une erreur pour l'audit.
    """
    log_entry = {
        "event": "ia_error",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id or "anonymous",
        "endpoint": endpoint,
        "erreur": erreur
    }
    logger.error(log_entry)