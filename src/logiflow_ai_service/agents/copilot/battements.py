"""Battements de cœur pendant l'attente du LLM.

Un LLM peut mettre du temps (outils, file d'attente du fournisseur) avant de produire son
premier token. Sans rien transmettre, Spring puis le navigateur considéreraient la connexion
morte (délai de lecture). `avec_battements` consomme la source dans un thread et intercale `None`
toutes les `intervalle_s` secondes de silence : l'orchestrateur le traduit en événement `attente`.
"""

import queue
import threading
from collections.abc import Iterable, Iterator

_VALEUR, _ERREUR, _FIN = "valeur", "erreur", "fin"


def avec_battements[T](source: Iterable[T], intervalle_s: float) -> Iterator[T | None]:
    file: queue.Queue[tuple[str, object]] = queue.Queue()
    arret = threading.Event()

    def consommer() -> None:
        iterateur = iter(source)
        try:
            for element in iterateur:
                file.put((_VALEUR, element))
                if arret.is_set():
                    break
        except BaseException as exc:  # relancée dans le thread du consommateur
            file.put((_ERREUR, exc))
        finally:
            fermer = getattr(iterateur, "close", None)
            if callable(fermer):
                fermer()  # ferme la connexion HTTP sous-jacente (le fournisseur cesse de générer)
            file.put((_FIN, None))

    threading.Thread(target=consommer, name="copilote-llm", daemon=True).start()
    try:
        while True:
            try:
                nature, valeur = file.get(timeout=intervalle_s)
            except queue.Empty:
                yield None
                continue
            if nature == _VALEUR:
                yield valeur  # type: ignore[misc]
            elif nature == _ERREUR:
                raise valeur  # type: ignore[misc]
            else:
                return
    finally:
        # Consommateur parti (Stop) ou fin normale : le thread s'arrête au prochain fragment.
        arret.set()
