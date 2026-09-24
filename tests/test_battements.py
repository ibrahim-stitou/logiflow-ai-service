import time

import pytest

from logiflow_ai_service.agents.copilot.battements import avec_battements


def _lente(*valeurs, pause=0.25):
    for valeur in valeurs:
        time.sleep(pause)
        yield valeur


def test_intercale_des_battements_pendant_le_silence():
    resultat = list(avec_battements(_lente("a", "b"), intervalle_s=0.05))

    assert [v for v in resultat if v is not None] == ["a", "b"]
    assert resultat.count(None) >= 2


def test_relance_l_erreur_de_la_source():
    def en_erreur():
        yield "a"
        raise RuntimeError("fournisseur coupé")

    iterateur = avec_battements(en_erreur(), intervalle_s=1)
    assert next(iterateur) == "a"
    with pytest.raises(RuntimeError, match="fournisseur coupé"):
        next(iterateur)


def test_fermeture_arrete_la_source():
    fermee = []

    def source():
        try:
            while True:
                time.sleep(0.02)
                yield "x"
        finally:
            fermee.append(True)

    iterateur = avec_battements(source(), intervalle_s=1)
    assert next(iterateur) == "x"
    iterateur.close()
    for _ in range(50):
        if fermee:
            break
        time.sleep(0.02)
    assert fermee == [True]
