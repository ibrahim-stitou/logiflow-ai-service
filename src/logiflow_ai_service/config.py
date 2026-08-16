"""Configuration de l'application, chargée depuis l'environnement (ou un fichier .env en local)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Sécurité service-à-service (voir docs/integration-ia.md côté backend) ---
    internal_api_key: str = "local-dev-key"

    # --- Ollama (LLM auto-hébergé) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_timeout_s: float = 30.0

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
