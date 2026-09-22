import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import requests

url = "http://localhost:8000/internal/ai/v1/copilot/ask"
headers = {"X-Internal-Api-Key": "logiflow-ai-secret-2026"}

questions = [
    "Quels camions sont disponibles demain ?",
    "Où en est le dossier DT-2026-001 ?",
    "Bonjour, comment ça va ?"
]

for q in questions:
    data = {"question": q}
    response = requests.post(url, json=data, headers=headers)
    print(f"❓ {q}")
    print(f"   Status: {response.status_code}")
    print(f"   Réponse: {response.json()}")
    print("-" * 60)