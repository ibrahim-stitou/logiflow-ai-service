"""Configuration de l'application, chargée depuis l'environnement (ou un fichier .env en local)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Sécurité service-à-service (voir docs/integration-ia.md côté backend) ---
    internal_api_key: str = "local-dev-key"

    # --- Base de données PROPRE au service IA (jamais la base TMS) ---
    # Conversations du copilote, messages, appels d'outils, feedback, base de connaissance.
    database_url: str = (
        "postgresql+psycopg://logiflow_ai:change-me-local-only@localhost:5433/logiflow_ai"
    )

    # --- Ollama (LLM auto-hébergé) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout_s: float = 30.0
    # Délai maximal entre deux fragments du flux : sur CPU, lire un prompt de ~1 500 tokens
    # (outils inclus) avant le premier token peut prendre plusieurs minutes.
    ollama_stream_timeout_s: float = 600.0
    ollama_num_ctx: int = 8192
    ollama_temperature: float = 0.2

    # --- Rappel des outils métier exposés par Spring Boot (/internal/copilote/**) ---
    backend_base_url: str = "http://localhost:8080"
    # Secret distinct d'internal_api_key : identifie le service IA auprès de Spring.
    backend_callback_api_key: str = "local-dev-callback-key"
    backend_timeout_s: float = 15.0

    # --- Copilote ---
    copilote_max_iterations_outils: int = 4
    copilote_historique_max: int = 20
    copilote_titre_llm: bool = True
    # Intervalle des événements `attente` émis tant que le LLM n'a rien produit.
    copilote_battement_s: float = 10.0

    # --- OSRM (routing / géolocalisation) ---
    # Démo publique par défaut ; à remplacer par une instance auto-hébergée en production
    # (cohérent avec Ollama : aucune dépendance à un service tiers payant).
    osrm_base_url: str = "https://router.project-osrm.org"
    osrm_timeout_s: float = 10.0

    # --- Application ---
    log_level: str = "INFO"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
