from datetime import UTC, datetime, timedelta

import httpx
import respx

from logiflow_ai_service.agents.planification.horaires import Evenement, ordonnancer
from logiflow_ai_service.agents.planification.matrice import matrice_haversine
from logiflow_ai_service.agents.planification.schemas import PlanificationRequest
from logiflow_ai_service.agents.planification.service import PlanificationService
from logiflow_ai_service.agents.planification.solveur import Solveur
from tests.llm_mock import CHAT

T0 = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)

SITES = {
    "lyon": (45.76, 4.84),
    "villeurbanne": (45.77, 4.88),
    "vienne": (45.52, 4.87),
    "marseille": (43.30, 5.37),
    "avignon": (43.95, 4.81),
    "paris": (48.85, 2.35),
}


def _fenetre(site, heures, duree=4):
    return {
        "siteId": site,
        "debut": (T0 + timedelta(hours=heures)).isoformat(),
        "fin": (T0 + timedelta(hours=heures + duree)).isoformat(),
    }


def _dossier(id_, de, vers, poids=4000, h_charge=0, h_decharge=5, **extra):
    return {
        "id": id_,
        "reference": f"DT-{id_}",
        "poidsBrutKg": poids,
        "volumeM3": 10,
        "nbPalettes": 6,
        "chargement": _fenetre(de, h_charge),
        "dechargement": _fenetre(vers, h_decharge, 6),
        **extra,
    }


def _payload(dossiers, type_voyage="GROUPAGE", nb_options=3, **extra):
    return {
        "debut": T0.isoformat(),
        "fin": (T0 + timedelta(days=2)).isoformat(),
        "typeVoyage": type_voyage,
        "nbOptions": nb_options,
        "dossiers": dossiers,
        "sites": [
            {"id": k, "libelle": k.capitalize(), "latitude": v[0], "longitude": v[1]}
            for k, v in SITES.items()
        ],
        "vehicules": [
            {"id": "tr1", "immatriculation": "TR-001-AA", "type": "TRACTEUR", "chargeUtileKg": 0},
            {
                "id": "po1",
                "immatriculation": "PO-001-AA",
                "type": "PORTEUR",
                "chargeUtileKg": 9000,
                "volumeUtileM3": 40,
                "nbPositionsPalettes": 18,
                "carrosserie": "TAUTLINER",
            },
        ],
        "remorques": [
            {
                "id": "re-taut",
                "immatriculation": "RE-001-AA",
                "carrosserie": "TAUTLINER",
                "chargeUtileKg": 24000,
                "volumeUtileM3": 90,
                "nbPositionsPalettes": 33,
            },
            {
                "id": "re-frigo",
                "immatriculation": "RE-002-AA",
                "carrosserie": "FRIGORIFIQUE",
                "chargeUtileKg": 22000,
                "volumeUtileM3": 80,
                "nbPositionsPalettes": 33,
                "groupeFroid": True,
                "temperatureMin": -25,
                "temperatureMax": 12,
            },
        ],
        "chauffeurs": [
            {
                "id": "ch-lyon",
                "matricule": "DRV-1",
                "nom": "Martin",
                "prenom": "Jean",
                "soldeTempsConduiteMinutes": 3000,
                "categoriesPermis": ["C", "CE"],
                "habilitations": ["ADR_BASE"],
                "siteRattachementId": "lyon",
            },
            {
                "id": "ch-paris",
                "matricule": "DRV-2",
                "nom": "Durand",
                "prenom": "Luc",
                "soldeTempsConduiteMinutes": 3000,
                "categoriesPermis": ["C", "CE"],
                "siteRattachementId": "paris",
            },
        ],
        **extra,
    }


def _solveur(payload):
    requete = PlanificationRequest.model_validate(payload)
    return Solveur(requete, matrice_haversine(SITES))


def _propositions(payload):
    propositions, non_planifiables = _solveur(payload).propositions()
    return {p.cle: p for p in propositions}, non_planifiables


def test_groupe_deux_dossiers_proches_et_respecte_la_precedence():
    payload = _payload(
        [
            _dossier("a", "lyon", "marseille"),
            _dossier("b", "villeurbanne", "avignon", h_decharge=4),
        ]
    )
    propositions, _ = _propositions(payload)

    groupe = propositions[frozenset({"a", "b"})]
    charges = set()
    for arret in groupe.tournee.arrets:
        charges.update(arret.charges)
        assert set(arret.decharges) <= charges
    # 8 t au plus à bord : le porteur bâché (9 t) est le plus petit support qui convient.
    assert groupe.support.vehicule.id == "po1"
    assert groupe.support.remorque is None
    assert groupe.chauffeurs[0].id == "ch-lyon"


def test_ne_melange_pas_adr_et_marchandise_ordinaire():
    payload = _payload(
        [
            _dossier("a", "lyon", "marseille", contientAdr=True),
            _dossier("b", "villeurbanne", "avignon", h_decharge=4),
        ]
    )
    propositions, _ = _propositions(payload)

    assert frozenset({"a", "b"}) not in propositions
    adr = propositions[frozenset({"a"})]
    assert [c.id for c in adr.chauffeurs] == ["ch-lyon"]


def test_frigo_exige_une_remorque_frigorifique_dans_la_plage():
    payload = _payload(
        [
            _dossier(
                "f", "lyon", "marseille", carrosserieRequise="FRIGORIFIQUE", temperatureRequise=4
            )
        ]
    )
    propositions, _ = _propositions(payload)

    assert propositions[frozenset({"f"})].support.remorque.id == "re-frigo"


def test_voyage_simple_ne_groupe_jamais():
    payload = _payload(
        [_dossier("a", "lyon", "marseille"), _dossier("b", "villeurbanne", "avignon")],
        type_voyage="SIMPLE",
    )
    propositions, _ = _propositions(payload)

    assert set(propositions) == {frozenset({"a"}), frozenset({"b"})}


def test_dossier_sans_support_assez_grand_est_non_planifiable():
    payload = _payload([_dossier("lourd", "lyon", "marseille", poids=30000)])
    propositions, non_planifiables = _propositions(payload)

    assert propositions == {}
    assert non_planifiables == ["DT-lourd"]


def test_ordonnancement_insere_les_pauses_et_attend_l_ouverture():
    matrice = matrice_haversine(SITES)
    evenements = [
        Evenement("a", "paris", True, T0, T0 + timedelta(hours=2)),
        Evenement("a", "marseille", False, T0 + timedelta(hours=14), T0 + timedelta(hours=20)),
    ]
    tournee = ordonnancer(evenements, matrice, T0)

    conduite = matrice.minutes("paris", "marseille")
    assert conduite > 540
    depart = tournee.arrets[0].etd
    pauses = int(conduite // 270)
    assert tournee.arrets[1].eta == depart + timedelta(minutes=conduite + pauses * 45)
    assert tournee.chauffeurs_requis == 2


def test_proposer_repli_haversine_et_gabarit(client, settings, auth_headers):
    payload = _payload(
        [
            _dossier("a", "lyon", "marseille"),
            _dossier("b", "villeurbanne", "avignon", h_decharge=4),
            _dossier("c", "vienne", "marseille", poids=2000),
        ]
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*/table/v1/driving/.*").mock(return_value=httpx.Response(503))
        mock.post(CHAT).mock(return_value=httpx.Response(500))
        response = client.post(
            "/internal/ai/v1/planification/proposer", json=payload, headers=auth_headers
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["sourceDistances"] == "HAVERSINE"
    assert body["sourceRedaction"] == "GABARIT"
    options = body["options"]
    assert 1 <= len(options) <= 3
    assert len({frozenset(o["dossierIds"]) for o in options}) == len(options)
    assert sum(o["recommandee"] for o in options) == 1
    premiere = options[0]
    assert premiere["arrets"][0]["dossiersCharges"]
    assert premiere["justification"]
    assert premiere["indicateurs"]["distanceKm"] > 0


def test_proposer_utilise_le_llm_pour_la_redaction(client, settings, auth_headers):
    payload = _payload(
        [_dossier("a", "lyon", "marseille"), _dossier("b", "villeurbanne", "avignon")],
        nb_options=2,
    )
    contenu = (
        '{"justifications": {"1": "Très bon remplissage."}, '
        '"comparaison": "Comparaison rédigée.", "recommandation": 1}'
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*/table/v1/driving/.*").mock(return_value=httpx.Response(503))
        mock.post(CHAT).mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": contenu}}]})
        )
        response = client.post(
            "/internal/ai/v1/planification/proposer", json=payload, headers=auth_headers
        )

    body = response.get_json()
    assert body["sourceRedaction"] == "LLM"
    assert body["comparaison"] == "Comparaison rédigée."
    assert body["options"][0]["justification"] == "Très bon remplissage."
    assert body["options"][0]["recommandee"] is True


def test_proposer_utilise_la_matrice_osrm(settings):
    requete = PlanificationRequest.model_validate(
        _payload([_dossier("a", "lyon", "marseille")], nb_options=1)
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*/table/v1/driving/.*").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "distances": [[0, 314_000], [314_000, 0]],
                    "durations": [[0, 12_000], [12_000, 0]],
                },
            )
        )
        from logiflow_ai_service.infrastructure.osrm_client import OsrmClient

        reponse = PlanificationService(OsrmClient(settings.osrm_base_url, 5), None).proposer(
            requete
        )

    assert reponse.source_distances == "OSRM"
    assert reponse.options[0].indicateurs.distance_km == 314.0


def test_proposer_avec_corps_invalide_renvoie_400(client, auth_headers):
    response = client.post("/internal/ai/v1/planification/proposer", json={}, headers=auth_headers)
    assert response.status_code == 400
