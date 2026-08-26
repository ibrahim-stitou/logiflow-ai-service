import requests

url = "http://localhost:8000/internal/ai/v1/maintenance/recommander"
headers = {"X-Internal-Api-Key": "logiflow-ai-secret-2026"}

data = {
    "vehicule": {
        "id": "12345",
        "kmDepuisVidange": 5000,
        "kmDepuisFreins": 10000,
        "kmDepuisPneus": 15000,
        "dateVisiteTechnique": "2026-01-01",
        "ageAns": 5,
        "nbPannes": 1
    }
}

print("📤 Envoi de la requête...")
print(f"Données: {data}")

response = requests.post(url, json=data, headers=headers)
print(f"\n📥 Réponse reçue:")
print(f"Status: {response.status_code}")

try:
    print(f"Response: {response.json()}")
except:
    print(f"Response (texte): {response.text}")