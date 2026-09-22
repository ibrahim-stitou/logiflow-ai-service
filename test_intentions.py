import sys
import os

# Ajouter le dossier src au PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from logiflow_ai_service.services.intent_detector import detecter_intention

questions = [
    "Quels camions sont disponibles demain ?",
    "Où en est le dossier DT-2026-001 ?",
    "Est-ce que je peux grouper DT-001 et DT-002 ?",
    "Combien de km entre Casablanca et Tanger ?",
    "Quand dois-je faire la vidange du camion ?",
    "Bonjour, comment ça va ?",
    "Quels véhicules sont libres aujourd'hui ?",
    "Montre-moi le dossier DT-123",
]

print("=" * 70)
for q in questions:
    intention, params = detecter_intention(q)
    print(f"❓ {q}")
    print(f"   → Intention: {intention}")
    print(f"   → Params: {params}")
    print("-" * 70)