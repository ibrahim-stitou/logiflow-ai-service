"""Orchestrateur d'une réponse du copilote : historique + LLM + boucle d'outils, en streaming.

`repondre()` est un générateur d'événements `(nom, données)` relayés tels quels en SSE (voir
`sse.py`). Déroulé :
1. persiste la question ;
2. reconstruit le contexte (prompt système + N derniers messages) ;
3. appelle le LLM avec le catalogue d'outils de l'utilisateur ; tant que le LLM demande des outils
   (dans la limite de `max_iterations_outils`), les exécute via Spring et relance le LLM ;
4. streame les tokens de la réponse finale, puis persiste la réponse et ses sources.

Tant que le LLM n'a rien produit (outils, file d'attente du fournisseur), un événement `attente`
est émis toutes les `battement_s` secondes pour que Spring et le navigateur gardent la connexion.

Si le client se déconnecte (bouton Stop → Spring ferme le flux), le générateur reçoit
`GeneratorExit` : la réponse partielle est persistée avec le statut `interrompu`.
"""

import json
import logging
import time
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

from logiflow_ai_service.agents.copilot.battements import avec_battements
from logiflow_ai_service.agents.copilot.model import (
    AppelOutil,
    Conversation,
    ConversationRepository,
    Message,
    Role,
    Source,
    StatutMessage,
)
from logiflow_ai_service.agents.copilot.outils import BoiteOutils, ContexteAppel, en_outils_llm
from logiflow_ai_service.agents.copilot.prompts import PROMPT_TITRE, prompt_systeme
from logiflow_ai_service.infrastructure.backend_client import ErreurOutil
from logiflow_ai_service.infrastructure.exceptions import LlmQuotaError, UpstreamServiceError
from logiflow_ai_service.infrastructure.llm_client import AppelOutilLlm, LlmClient

logger = logging.getLogger(__name__)

Evenement = tuple[str, dict[str, Any]]

TITRE_PAR_DEFAUT = "Nouvelle conversation"
_LONGUEUR_MAX_RESULTAT_OUTIL = 12_000


class CopiloteOrchestrateur:
    def __init__(
        self,
        repository: ConversationRepository,
        llm: LlmClient,
        outils: BoiteOutils,
        *,
        max_iterations_outils: int,
        historique_max: int,
        titre_llm: bool,
        aujourd_hui: Callable[[], date] = date.today,
        battement_s: float = 10.0,
    ) -> None:
        self._battement_s = battement_s
        self._repository = repository
        self._llm = llm
        self._outils = outils
        self._max_iterations = max_iterations_outils
        self._historique_max = historique_max
        self._titre_llm = titre_llm
        self._aujourd_hui = aujourd_hui

    def repondre(
        self, conversation: Conversation, question: str, contexte: ContexteAppel
    ) -> Iterator[Evenement]:
        historique = self._repository.messages(conversation.id, limite=self._historique_max)
        self._repository.enregistrer_message(
            Message(conversation_id=conversation.id, role=Role.UTILISATEUR, contenu=question)
        )
        reponse = Message(
            conversation_id=conversation.id,
            role=Role.ASSISTANT,
            contenu="",
            statut=StatutMessage.EN_COURS,
            modele=self._llm.model,
        )
        # Persistée dès maintenant : les appels d'outils y font référence (clé étrangère).
        self._repository.enregistrer_message(reponse)
        yield "meta", {"conversationId": str(conversation.id), "messageId": str(reponse.id)}

        debut = time.monotonic()
        try:
            yield from self._generer(reponse, historique, question, contexte)
            reponse.statut = StatutMessage.COMPLET
        except GeneratorExit:
            reponse.statut = StatutMessage.INTERROMPU
            raise
        except LlmQuotaError as exc:
            logger.warning("Quota LLM atteint : %s", exc)
            reponse.statut = StatutMessage.ERREUR
            yield (
                "erreur",
                {
                    "code": "QUOTA_LLM",
                    "message": "Quota du fournisseur IA atteint (palier gratuit). "
                    "Réessayez dans une minute.",
                },
            )
        except UpstreamServiceError as exc:
            logger.warning("Réponse du copilote impossible : %s", exc)
            reponse.statut = StatutMessage.ERREUR
            yield (
                "erreur",
                {
                    "code": "LLM_INDISPONIBLE",
                    "message": "Le moteur IA est momentanément indisponible. Réessayez plus tard.",
                },
            )
        finally:
            reponse.duree_ms = int((time.monotonic() - debut) * 1000)
            self._repository.enregistrer_message(reponse)

        if reponse.statut is not StatutMessage.COMPLET:
            return
        if reponse.sources:
            yield "sources", {"sources": [s.en_dict() for s in reponse.sources]}
        titre = self._titre_si_premier_echange(conversation, historique, question)
        if titre:
            yield "titre", {"titre": titre}
        yield (
            "fin",
            {
                "messageId": str(reponse.id),
                "tokensPrompt": reponse.tokens_prompt,
                "tokensCompletion": reponse.tokens_completion,
                "dureeMs": reponse.duree_ms,
            },
        )

    def _generer(
        self,
        reponse: Message,
        historique: list[Message],
        question: str,
        contexte: ContexteAppel,
    ) -> Iterator[Evenement]:
        catalogue = self._catalogue(contexte)
        libelles = {o["nom"]: o.get("libelle") or o["nom"] for o in catalogue}
        outils_llm = en_outils_llm(catalogue)

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": prompt_systeme(
                    contexte.nom, contexte.roles, self._aujourd_hui(), bool(catalogue)
                ),
            },
            *(
                {"role": m.role.value, "content": m.contenu}
                for m in historique
                if m.statut is StatutMessage.COMPLET and m.contenu
            ),
            {"role": "user", "content": question},
        ]
        sources: dict[tuple[str, str], Source] = {}

        for iteration in range(self._max_iterations + 1):
            # Au dernier tour, plus d'appel d'outil : on force le LLM à conclure avec ce qu'il a.
            dernier_tour = iteration == self._max_iterations
            texte_du_tour = ""
            appels: list[AppelOutilLlm] = []
            flux = self._llm.chat_stream(messages, outils_llm or None, forcer_reponse=dernier_tour)
            for fragment in avec_battements(flux, self._battement_s):
                if fragment is None:
                    yield "attente", {}
                    continue
                if fragment.contenu:
                    texte_du_tour += fragment.contenu
                    reponse.contenu += fragment.contenu
                    yield "token", {"texte": fragment.contenu}
                appels.extend(fragment.appels_outils)
                if fragment.fini:
                    reponse.tokens_prompt = _somme(reponse.tokens_prompt, fragment.tokens_prompt)
                    reponse.tokens_completion = _somme(
                        reponse.tokens_completion, fragment.tokens_completion
                    )
            if not appels:
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": texte_du_tour or None,
                    "tool_calls": [
                        {
                            "id": appel.id,
                            "type": "function",
                            "function": {
                                "name": appel.nom,
                                "arguments": json.dumps(appel.arguments, ensure_ascii=False),
                            },
                        }
                        for appel in appels
                    ],
                }
            )
            for appel in appels:
                nom, arguments = appel.nom, appel.arguments
                libelle = libelles.get(nom, nom)
                yield "outil", {"nom": nom, "libelle": libelle, "statut": "debut"}
                resultat = self._executer_outil(reponse, nom, arguments, libelles, contexte)
                for source in resultat.get("sources") or []:
                    try:
                        s = Source(
                            type=str(source["type"]),
                            reference=str(source["reference"]),
                            id=source.get("id"),
                        )
                    except (KeyError, TypeError):
                        continue
                    sources.setdefault(s.cle(), s)
                yield (
                    "outil",
                    {
                        "nom": nom,
                        "libelle": libelle,
                        "statut": "erreur" if "erreur" in resultat else "fin",
                    },
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": appel.id,
                        "content": json.dumps(resultat, ensure_ascii=False, default=str)[
                            :_LONGUEUR_MAX_RESULTAT_OUTIL
                        ],
                    }
                )
        reponse.sources = list(sources.values())

    def _catalogue(self, contexte: ContexteAppel) -> list[dict[str, Any]]:
        try:
            return self._outils.catalogue(contexte)
        except UpstreamServiceError:
            # Dégradation : sans outils, le copilote répond encore aux questions générales.
            logger.warning("Catalogue d'outils indisponible : réponse sans données métier")
            return []

    def _executer_outil(
        self,
        reponse: Message,
        nom: str,
        arguments: dict[str, Any],
        libelles: dict[str, str],
        contexte: ContexteAppel,
    ) -> dict[str, Any]:
        debut = time.monotonic()
        erreur: str | None = None
        resultat: dict[str, Any]
        if nom not in libelles:
            erreur = f"Outil inconnu : {nom}. Outils disponibles : {', '.join(libelles)}."
        else:
            try:
                resultat = self._outils.executer(nom, arguments, contexte)
            except ErreurOutil as exc:
                erreur = str(exc)
            except UpstreamServiceError as exc:
                logger.warning("Outil %s indisponible : %s", nom, exc)
                erreur = "Source de données momentanément indisponible."
        if erreur is not None:
            resultat = {"erreur": erreur}
        self._repository.enregistrer_appel_outil(
            AppelOutil(
                message_id=reponse.id,
                nom=nom,
                arguments=arguments,
                succes=erreur is None,
                duree_ms=int((time.monotonic() - debut) * 1000),
                nb_resultats=resultat.get("total") if erreur is None else None,
                erreur=erreur,
            )
        )
        return resultat

    def _titre_si_premier_echange(
        self, conversation: Conversation, historique: list[Message], question: str
    ) -> str | None:
        if historique or conversation.titre != TITRE_PAR_DEFAUT:
            return None
        titre = _titre_depuis_question(question)
        if self._titre_llm:
            try:
                propose = self._llm.chat(PROMPT_TITRE, question).strip().strip("\"'«» .")
                if 0 < len(propose) <= 80:
                    titre = propose
            except UpstreamServiceError:
                logger.info("Titre LLM indisponible, repli sur la question tronquée")
        conversation.titre = titre
        self._repository.renommer(conversation.id, conversation.utilisateur_id, titre)
        return titre


def _somme(a: int | None, b: int | None) -> int | None:
    if b is None:
        return a
    return (a or 0) + b


def _titre_depuis_question(question: str) -> str:
    titre = " ".join(question.split())
    return titre if len(titre) <= 60 else titre[:57].rstrip() + "…"
