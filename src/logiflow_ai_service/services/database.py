"""
Base de données IA pour LogiFlow.
Stocke : résultats IA, prédictions, historique chat, embeddings, requêtes.
"""

import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, JSON

# Initialiser SQLAlchemy
db = SQLAlchemy()


# ==================== MODÈLES ====================

class AIResult(db.Model):
    """Résultats des analyses IA."""
    __tablename__ = "ai_results"
    
    id = Column(Integer, primary_key=True)
    type_analyse = Column(String(50))
    dossier_ids = Column(JSON)
    score = Column(Float)
    gain_km = Column(Float, nullable=True)
    resultat = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Prediction(db.Model):
    """Prédictions (maintenance, retards)."""
    __tablename__ = "predictions"
    
    id = Column(Integer, primary_key=True)
    vehicule_id = Column(String(50))
    type_prediction = Column(String(50))
    score = Column(Float)
    date_predite = Column(DateTime)
    confiance = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)


class ChatHistory(db.Model):
    """Historique des conversations."""
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100))
    question = Column(Text)
    reponse = Column(Text)
    intention = Column(String(50))
    timestamp = Column(DateTime, default=datetime.utcnow)


class AIRequest(db.Model):
    """Requêtes IA pour l'audit."""
    __tablename__ = "ai_requests"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100))
    endpoint = Column(String(100))
    question = Column(Text)
    succes = Column(Boolean, default=True)
    duree_ms = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Embedding(db.Model):
    """Embeddings pour RAG."""
    __tablename__ = "embeddings"
    
    id = Column(Integer, primary_key=True)
    source = Column(String(100))
    contenu = Column(Text)
    vecteur = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)


# ==================== INITIALISATION ====================

def init_db(app):
    """Initialise la base de données PostgreSQL."""
    db_user = os.getenv("DB_USER", "logiflow_ai")
    db_password = os.getenv("DB_PASSWORD", "logiflow_ai_password")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "logiflow_ai")
    
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    db.init_app(app)
    
    with app.app_context():
        try:
            db.create_all()
            print("✅ Base de données IA initialisée (PostgreSQL)")
        except Exception as e:
            print(f"❌ Erreur base de données : {e}")


# ==================== FONCTIONS ====================

def sauvegarder_resultat(type_analyse, dossier_ids, score, gain_km, resultat):
    """Sauvegarde un résultat d'analyse IA."""
    try:
        ai_result = AIResult(
            type_analyse=type_analyse,
            dossier_ids=dossier_ids,
            score=score,
            gain_km=gain_km,
            resultat=resultat
        )
        db.session.add(ai_result)
        db.session.commit()
        return ai_result.id
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur sauvegarde résultat: {e}")
        return None


def sauvegarder_chat(user_id, question, reponse, intention):
    """Sauvegarde un échange avec le chatbot."""
    try:
        chat = ChatHistory(
            user_id=user_id,
            question=question,
            reponse=reponse,
            intention=intention
        )
        db.session.add(chat)
        db.session.commit()
        return chat.id
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur sauvegarde chat: {e}")
        return None


def sauvegarder_requete(user_id, endpoint, question, succes, duree_ms):
    """Sauvegarde une requête IA pour l'audit."""
    try:
        req = AIRequest(
            user_id=user_id,
            endpoint=endpoint,
            question=question,
            succes=succes,
            duree_ms=duree_ms
        )
        db.session.add(req)
        db.session.commit()
        return req.id
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur sauvegarde requête: {e}")
        return None


def get_historique_chat(user_id, limit=10):
    """Récupère l'historique des chats d'un utilisateur."""
    return ChatHistory.query.filter_by(user_id=user_id)\
        .order_by(ChatHistory.timestamp.desc())\
        .limit(limit).all()