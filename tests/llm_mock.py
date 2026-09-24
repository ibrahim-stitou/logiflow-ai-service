"""Réponses simulées d'un fournisseur LLM compatible OpenAI (/chat/completions)."""

import json
from typing import Any

import httpx

LLM = "http://llm.test/v1"
CHAT = f"{LLM}/chat/completions"


def sse(*morceaux: dict[str, Any]) -> httpx.Response:
    lignes = [f"data: {json.dumps(m)}\n\n" for m in morceaux] + ["data: [DONE]\n\n"]
    return httpx.Response(
        200, content="".join(lignes).encode(), headers={"Content-Type": "text/event-stream"}
    )


def _delta(delta: dict[str, Any], fin: str | None = None) -> dict[str, Any]:
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": fin}]}


def texte(*fragments: str, prompt: int = 10, completion: int = 5) -> httpx.Response:
    """Réponse texte streamée ; l'usage arrive dans le dernier morceau (façon Groq)."""
    return sse(
        *(_delta({"content": f}) for f in fragments),
        {
            **_delta({}, "stop"),
            "x_groq": {"usage": {"prompt_tokens": prompt, "completion_tokens": completion}},
        },
    )


def appel_outil(nom: str, arguments: dict[str, Any], id_appel: str = "call_1") -> httpx.Response:
    """Appel d'outil dont les arguments JSON arrivent en deux morceaux (cas réel)."""
    brut = json.dumps(arguments)
    milieu = len(brut) // 2
    return sse(
        _delta(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": id_appel,
                        "type": "function",
                        "function": {"name": nom, "arguments": brut[:milieu]},
                    }
                ]
            }
        ),
        _delta({"tool_calls": [{"index": 0, "function": {"arguments": brut[milieu:]}}]}),
        {**_delta({}, "tool_calls"), "usage": {"prompt_tokens": 7, "completion_tokens": 2}},
    )


def reponse_chat(contenu: str) -> httpx.Response:
    """Réponse non streamée (titres, ancienne route /copilot/ask)."""
    return httpx.Response(200, json={"choices": [{"message": {"content": contenu}}]})
