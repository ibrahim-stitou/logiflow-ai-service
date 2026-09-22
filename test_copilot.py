import requests

url = "http://localhost:8000/internal/ai/v1/copilot/ask"
headers = {"X-Internal-Api-Key": "logiflow-ai-secret-2026"}
data = {"question": "donne-moi les mois de l'année ?"}

print("📤 Envoi de la requête...")
response = requests.post(url, json=data, headers=headers)
print(f"📥 Status: {response.status_code}")
print(f"📥 Response: {response.text}")