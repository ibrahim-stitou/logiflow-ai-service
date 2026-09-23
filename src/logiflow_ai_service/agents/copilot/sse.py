"""Sérialisation Server-Sent Events : `event: <nom>` + `data: <json sur une ligne>`."""

import json
from typing import Any


def evenement_sse(nom: str, donnees: dict[str, Any]) -> str:
    return f"event: {nom}\ndata: {json.dumps(donnees, ensure_ascii=False, default=str)}\n\n"
