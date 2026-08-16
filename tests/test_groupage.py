def _dossier(id_, poids=8000, volume=10.0, palettes=10, adr=False):
    return {
        "id": id_,
        "reference": f"DT-{id_}",
        "poidsBrutKg": poids,
        "volumeM3": volume,
        "nbPalettes": palettes,
        "contientAdr": adr,
    }


def test_analyser_propose_un_groupage_compatible(client, auth_headers):
    payload = {
        "dossiers": [_dossier("d1"), _dossier("d2", poids=300, volume=1.5, palettes=5)],
        "correlationId": "corr-1",
    }
    response = client.post("/internal/ai/v1/groupage/analyser", json=payload, headers=auth_headers)

    assert response.status_code == 200
    propositions = response.get_json()["propositions"]
    assert len(propositions) == 1
    assert set(propositions[0]["dossierIds"]) == {"d1", "d2"}
    assert propositions[0]["gainKm"] is None


def test_analyser_ignore_les_paires_adr_incompatibles(client, auth_headers):
    payload = {
        "dossiers": [_dossier("d1", adr=True), _dossier("d2", adr=False)],
        "correlationId": "corr-2",
    }
    response = client.post("/internal/ai/v1/groupage/analyser", json=payload, headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["propositions"] == []


def test_analyser_refuse_une_paire_qui_depasse_la_capacite(client, auth_headers):
    payload = {
        "dossiers": [_dossier("d1", poids=15000), _dossier("d2", poids=15000)],
        "correlationId": "corr-3",
    }
    response = client.post("/internal/ai/v1/groupage/analyser", json=payload, headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["propositions"] == []


def test_analyser_avec_corps_invalide_renvoie_400(client, auth_headers):
    response = client.post("/internal/ai/v1/groupage/analyser", json={}, headers=auth_headers)
    assert response.status_code == 400
