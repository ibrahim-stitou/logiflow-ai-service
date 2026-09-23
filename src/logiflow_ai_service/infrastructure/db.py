"""Connexion à la base propre du service IA (`logiflow_ai`).

L'engine est créé paresseusement : aucune connexion n'est ouverte au démarrage, si bien que les
agents sans base (groupage, itinéraire) restent disponibles même si PostgreSQL ne l'est pas.
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def creer_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def creer_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
