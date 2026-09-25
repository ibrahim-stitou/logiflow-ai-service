from datetime import UTC, datetime, timedelta

import httpx
import respx

from logiflow_ai_service.agents.maintenance.analyse import (
    analyser,
    creneau_libre,
    echeances_plans,
)
from logiflow_ai_service.agents.maintenance.schemas import (
    MaintenanceRequest,
    VehiculeAAnalyser,
)
from tests.llm_mock import CHAT

T0 = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def _vehicule(id_="v1", **extra):
    base = {
        "id": id_,
        "immatriculation": f"AB-{id_}",
        "type": "TRACTEUR",
        "statut": "DISPONIBLE",
        "kilometrage": 150_000,
        "kmRealises": 27_000,  # 300 km/jour
        "litresConsommes": 8_100,  # 30 L/100
        "plans": [
            {
                "id": "p1",
                "libelle": "Révision",
                "periodiciteKm": 40_000,
                "periodiciteMois": 12,
                "seuilAlerteKm": 2_000,
                "dureeEstimeeMin": 120,
            }
        ],
    }
    return {**base, **extra}


def _requete(*vehicules, horizon=30):
    return MaintenanceRequest.model_validate(
        {"dateReference": T0.isoformat(), "horizonJours": horizon, "vehicules": list(vehicules)}
    )


def _ot(type_, statut, jours):
    return {
        "type": type_,
        "statut": statut,
        "datePlanifiee": (T0 + timedelta(days=jours)).isoformat(),
    }


def test_echeance_depuis_le_dernier_entretien_et_l_usage_reel():
    v = VehiculeAAnalyser.model_validate(
        _vehicule(ordres=[_ot("ENTRETIEN_PREVENTIF", "TERMINE", -120)])
    )
    (echeance,) = echeances_plans(v, T0.date(), 30)

    # 120 jours × 300 km = 36 000 km depuis la révision : il en reste 4 000, soit ~13 jours.
    assert echeance.echeance.km_restant == 4_000
    assert echeance.echeance.date_echeance == T0.date() + timedelta(days=13)
    assert echeance.echeance.en_alerte


def test_les_voyages_planifies_avancent_l_echeance():
    voyage = {
        "reference": "VOY-1",
        "depart": (T0 + timedelta(days=2)).isoformat(),
        "arrivee": (T0 + timedelta(days=3)).isoformat(),
        "distanceKm": 5_000,
    }
    v = VehiculeAAnalyser.model_validate(
        _vehicule(ordres=[_ot("ENTRETIEN_PREVENTIF", "TERMINE", -120)], voyagesPlanifies=[voyage])
    )
    (echeance,) = echeances_plans(v, T0.date(), 30)

    assert echeance.echeance.date_echeance == T0.date() + timedelta(days=2)


def test_creneau_libre_entre_deux_voyages():
    voyages = [
        {
            "reference": "VOY-1",
            "depart": datetime(2026, 9, 25, 6, tzinfo=UTC).isoformat(),
            "arrivee": datetime(2026, 9, 25, 18, tzinfo=UTC).isoformat(),
        },
        {
            "reference": "VOY-2",
            "depart": datetime(2026, 9, 26, 12, tzinfo=UTC).isoformat(),
            "arrivee": datetime(2026, 9, 27, 18, tzinfo=UTC).isoformat(),
        },
    ]
    v = VehiculeAAnalyser.model_validate(_vehicule(voyagesPlanifies=voyages))

    debut, fin = creneau_libre(v, T0, None, 180)

    assert debut == datetime(2026, 9, 26, 7, tzinfo=UTC)
    assert fin == datetime(2026, 9, 26, 10, tzinfo=UTC)


def test_score_documents_reparations_et_surconsommation():
    sain = [
        _vehicule(f"s{i}", ordres=[_ot("ENTRETIEN_PREVENTIF", "TERMINE", -10)]) for i in range(3)
    ]
    risque = _vehicule(
        "r1",
        litresConsommes=11_000,  # ≈ 40,7 L/100 contre 30 pour la flotte
        ordres=[
            _ot("ENTRETIEN_PREVENTIF", "TERMINE", -10),
            _ot("REPARATION", "TERMINE", -40),
            _ot("REPARATION", "TERMINE", -15),
        ],
        documents=[{"type": "CONTROLE_TECHNIQUE", "dateExpiration": "2026-09-20"}],
    )
    analyses = {a.vehicule_id: a for a in analyser(_requete(*sain, risque))}

    assert analyses["s0"].statut == "BON"
    r = analyses["r1"]
    # 100 - 30 - 15 - 10 = 45, plafonné à 39 : contrôle technique expiré.
    assert r.score == 39
    assert r.statut == "CRITIQUE"
    assert r.recommandations[0].priorite == "URGENTE"
    assert r.recommandations[0].type == "CONTROLE_TECHNIQUE"
    assert any("réparations" in a for a in r.anomalies)
    assert any("Consommation" in a for a in r.anomalies)


def test_un_entretien_deja_planifie_n_est_pas_re_propose_en_premier():
    v = _vehicule(
        ordres=[
            _ot("ENTRETIEN_PREVENTIF", "TERMINE", -130),
            _ot("ENTRETIEN_PREVENTIF", "PLANIFIE", 3),
        ]
    )
    (analyse,) = analyser(_requete(v))

    assert analyse.recommandations[0].deja_planifie


def test_route_recommander_avec_repli_gabarit(client, auth_headers):
    payload = {
        "dateReference": T0.isoformat(),
        "vehicules": [_vehicule(ordres=[_ot("ENTRETIEN_PREVENTIF", "TERMINE", -135)])],
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.post(CHAT).mock(return_value=httpx.Response(500))
        response = client.post(
            "/internal/ai/v1/maintenance/recommander", json=payload, headers=auth_headers
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["sourceRedaction"] == "GABARIT"
    vehicule = body["vehicules"][0]
    assert vehicule["statut"] in {"A_PLANIFIER", "CRITIQUE", "SURVEILLER"}
    assert vehicule["recommandations"][0]["type"] == "ENTRETIEN_PREVENTIF"
    assert vehicule["explication"].startswith("Score")
    assert "engin(s) analysé(s)" in body["synthese"]


def test_route_recommander_avec_llm(client, auth_headers):
    payload = {
        "dateReference": T0.isoformat(),
        "vehicules": [_vehicule(ordres=[_ot("ENTRETIEN_PREVENTIF", "TERMINE", -135)])],
    }
    contenu = '{"explications": {"AB-v1": "Révision imminente."}, "synthese": "Flotte saine."}'
    with respx.mock(assert_all_called=False) as mock:
        mock.post(CHAT).mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": contenu}}]})
        )
        response = client.post(
            "/internal/ai/v1/maintenance/recommander", json=payload, headers=auth_headers
        )

    body = response.get_json()
    assert body["sourceRedaction"] == "LLM"
    assert body["synthese"] == "Flotte saine."
    assert body["vehicules"][0]["explication"] == "Révision imminente."


def test_route_recommander_corps_invalide(client, auth_headers):
    response = client.post("/internal/ai/v1/maintenance/recommander", json={}, headers=auth_headers)
    assert response.status_code == 400


def _plan_calcule(**extra):
    """Plan dont Spring fournit la dernière réalisation et l'échéance."""
    return {
        "id": "p9",
        "libelle": "Contrôle groupe froid",
        "type": "GROUPE_FROID",
        "periodiciteKm": 60_000,
        "seuilAlerteKm": 3_000,
        "dureeEstimeeMin": 180,
        "derniereKm": 90_000,
        **extra,
    }


def test_l_echeance_calculee_par_spring_prime_sur_l_estimation():
    v = VehiculeAAnalyser.model_validate(
        _vehicule(
            plans=[_plan_calcule(kmRestant=-500, dateEcheance="2026-09-20", etat="ECHU")],
            # Un ancien préventif terminé ne doit plus servir d'origine.
            ordres=[_ot("ENTRETIEN_PREVENTIF", "TERMINE", -10)],
        )
    )
    (analyse,) = analyser(_requete(v.model_dump(by_alias=True)))

    recommandation = analyse.recommandations[0]
    assert analyse.km_avant_echeance == -500
    assert recommandation.type == "GROUPE_FROID"
    assert recommandation.priorite == "URGENTE"
    assert recommandation.creneau_debut is not None
    assert analyse.statut == "CRITIQUE"


def test_un_ot_rattache_au_plan_marque_l_echeance_deja_planifiee():
    ot = {**_ot("GROUPE_FROID", "PLANIFIE", -30), "planId": "p9"}
    v = VehiculeAAnalyser.model_validate(
        _vehicule(plans=[_plan_calcule(kmRestant=1_000, etat="ALERTE")], ordres=[ot])
    )
    (echeance,) = echeances_plans(v, T0.date(), 30)

    assert echeance.deja_planifie
    assert echeance.echeance.en_alerte


def test_sinistralite_et_engin_immobilise_par_un_sinistre():
    sinistres = [
        {
            "reference": "SIN-2026-000001",
            "dateSurvenance": "2026-03-02",
            "type": "ACCROCHAGE",
            "gravite": "MATERIEL_LEGER",
            "responsabilite": "RESPONSABLE",
            "statut": "CLOS",
            "coutNet": 1200,
        },
        {
            "reference": "SIN-2026-000002",
            "dateSurvenance": "2026-09-18",
            "type": "BRIS_DE_GLACE",
            "gravite": "MATERIEL_LEGER",
            "statut": "EN_EXPERTISE",
            "enginImmobilise": True,
            "coutNet": 300,
        },
    ]
    sans = analyser(_requete(_vehicule(plans=[])))[0]
    (analyse,) = analyser(_requete(_vehicule(plans=[], sinistres=sinistres)))

    assert analyse.score == sans.score - 25
    assert any(
        "2 sinistres en 12 mois (coût net 1500 €), dont 1 en tort" in a for a in analyse.anomalies
    )
    assert any("SIN-2026-000002" in a for a in analyse.anomalies)
    reparation = next(r for r in analyse.recommandations if "SIN-2026-000002" in r.libelle)
    assert reparation.type == "CARROSSERIE"
    assert reparation.priorite == "HAUTE"
    assert not reparation.deja_planifie

    ot = {**_ot("CARROSSERIE", "EN_COURS", -1), "origine": "SINISTRE"}
    (suivie,) = analyser(_requete(_vehicule(plans=[], sinistres=sinistres, ordres=[ot])))
    assert next(r for r in suivie.recommandations if "SIN-2026-000002" in r.libelle).deja_planifie


def test_une_remorque_est_analysee_sans_consommation():
    remorque = _vehicule(
        "r1",
        typeEngin="REMORQUE",
        type="FRIGORIFIQUE",
        litresConsommes=0,
        documents=[{"type": "CONTROLE_TECHNIQUE", "dateExpiration": "2026-09-01"}],
    )
    analyses = analyser(_requete(remorque, _vehicule("v2"), _vehicule("v3"), _vehicule("v4")))
    analyse = next(a for a in analyses if a.vehicule_id == "r1")

    assert analyse.type_engin == "REMORQUE"
    assert analyse.consommation_l100 is None
    ct = next(r for r in analyse.recommandations if r.type == "CONTROLE_TECHNIQUE")
    assert "la remorque ne peut pas être affecté(e)" in ct.justification


def test_route_recommander_renvoie_le_type_d_engin(client, auth_headers):
    corps = {
        "dateReference": T0.isoformat(),
        "horizonJours": 30,
        "vehicules": [_vehicule("r1", typeEngin="REMORQUE", plans=[_plan_calcule(etat="OK")])],
    }
    with respx.mock:
        respx.post(CHAT).mock(return_value=httpx.Response(500))
        reponse = client.post(
            "/internal/ai/v1/maintenance/recommander", json=corps, headers=auth_headers
        )

    assert reponse.status_code == 200
    assert reponse.get_json()["vehicules"][0]["typeEngin"] == "REMORQUE"
