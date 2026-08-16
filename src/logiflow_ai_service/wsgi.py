"""Point d'entrée WSGI pour gunicorn (production) : `gunicorn logiflow_ai_service.wsgi:app`."""

from logiflow_ai_service.app import create_app

app = create_app()
