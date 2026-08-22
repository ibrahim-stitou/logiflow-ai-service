import os
import requests
import logging

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("LLM_MODEL", "llama3.1")

def call_ollama(prompt: str, temperature: float = 0.7) -> str:
    """Appelle le modèle Ollama et retourne la réponse."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature}
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json().get("response", "Pas de réponse")
        return f"Erreur: {response.status_code}"
    except Exception as e:
        logger.error(f"Erreur Ollama: {e}")
        return "Service IA indisponible. Mode dégradé."