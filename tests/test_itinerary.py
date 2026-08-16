import httpx
import respx

_OSRM_ROUTE_OK = {
    "code": "Ok",
    "routes": [
        {
            "distance": 465_300.0,
            "duration": 15_504.0,
            "legs": [{"distance": 465_300.0, "duration": 15_504.0}],
        }
    ],
}

_POINTS = [
    {"latitude": 48.8566, "longitude": 2.3522, "libelle": "Paris"},
    {"latitude": 45.7640, "longitude": 4.8357, "libelle": "Lyon"},
]


def test_calculer_renvoie_un_itineraire(client, settings, auth_headers):
    with respx.mock(base_url=settings.osrm_base_url) as mock:
        mock.get(url__regex=r"/route/v1/driving/.*").mock(
            return_value=httpx.Response(200, json=_OSRM_ROUTE_OK)
        )
        payload = {"points": _POINTS, "correlationId": "corr-1"}
        response = client.post(
            "/internal/ai/v1/itinerary/calculer", json=payload, headers=auth_headers
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["distanceKm"] == 465.3
    assert len(body["segments"]) == 1
    assert body["segments"][0]["depart"]["libelle"] == "Paris"


def test_calculer_renvoie_503_si_osrm_indisponible(client, settings, auth_headers):
    with respx.mock(base_url=settings.osrm_base_url) as mock:
        mock.get(url__regex=r"/route/v1/driving/.*").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        payload = {"points": _POINTS}
        response = client.post(
            "/internal/ai/v1/itinerary/calculer", json=payload, headers=auth_headers
        )

    assert response.status_code == 503


def test_calculer_refuse_moins_de_deux_points(client, auth_headers):
    payload = {"points": [_POINTS[0]]}
    response = client.post("/internal/ai/v1/itinerary/calculer", json=payload, headers=auth_headers)
    assert response.status_code == 400
