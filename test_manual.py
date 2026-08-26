import requests
import json

url = "http://localhost:8000/internal/ai/v1/groupage/analyser"
headers = {"X-Internal-Api-Key": "logiflow-ai-secret-2026"}

data = {
    "candidats": [
        {
            "id": "1111",
            "reference": "DT-001",
            "poidsBrutKg": 1500.5,
            "volumeM3": 12.0,
            "nbPalettes": 4,
            "contientAdr": False,
            "groupable": True,
            "siteChargementLat": 33.5731,
            "siteChargementLon": -7.5898,
            "dateDechargement": "2026-08-26",
            "carrosserieRequise": "PLATEAU"
        },
        {
            "id": "2222",
            "reference": "DT-002",
            "poidsBrutKg": 800.0,
            "volumeM3": 8.0,
            "nbPalettes": 2,
            "contientAdr": False,
            "groupable": True,
            "siteChargementLat": 33.5731,
            "siteChargementLon": -7.5898,
            "dateDechargement": "2026-08-27",
            "carrosserieRequise": "PLATEAU"
        }
    ]
}

response = requests.post(url, json=data, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
