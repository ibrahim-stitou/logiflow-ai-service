"""Commandes CLI Flask : `flask --app logiflow_ai_service.app:create_app ingerer <fichiers...>`.

Ingestion de la base de connaissance du copilote : chaque fichier (.md, .txt, .html) est découpé
en fragments, vectorisé par le fournisseur d'embeddings (`EMBED_MODEL`) puis stocké dans
`logiflow_ai`. Une réingestion remplace la version précédente du document.
"""

import html
import re
from pathlib import Path

import click
from flask import Flask, current_app

_TAILLE_FRAGMENT = 3000  # caractères (~800 tokens)
_CHEVAUCHEMENT = 300
_LOT_EMBEDDINGS = 16


def texte_depuis_fichier(chemin: Path) -> tuple[str, str]:
    """(titre, texte brut) d'un fichier ; le HTML est réduit à son texte."""
    brut = chemin.read_text(encoding="utf-8")
    titre = chemin.stem
    if chemin.suffix.lower() in {".html", ".htm"}:
        if m := re.search(r"<title>(.*?)</title>", brut, re.IGNORECASE | re.DOTALL):
            titre = html.unescape(m.group(1).strip())
        brut = re.sub(r"<(script|style)\b.*?</\1>", " ", brut, flags=re.IGNORECASE | re.DOTALL)
        brut = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)\b[^>]*>", "\n", brut, flags=re.IGNORECASE)
        brut = html.unescape(re.sub(r"<[^>]+>", " ", brut))
    elif m := re.search(r"^#\s+(.+)$", brut, re.MULTILINE):
        titre = m.group(1).strip()
    texte = re.sub(r"[ \t]+", " ", brut)
    texte = re.sub(r"\n\s*\n+", "\n\n", texte).strip()
    return titre, texte


def decouper(texte: str) -> list[str]:
    """Fragments d'environ `_TAILLE_FRAGMENT` caractères, coupés sur les paragraphes."""
    fragments: list[str] = []
    courant = ""
    for paragraphe in texte.split("\n\n"):
        while len(paragraphe) > _TAILLE_FRAGMENT:
            fragments.append(paragraphe[:_TAILLE_FRAGMENT])
            paragraphe = paragraphe[_TAILLE_FRAGMENT - _CHEVAUCHEMENT :]
        if len(courant) + len(paragraphe) + 2 > _TAILLE_FRAGMENT and courant:
            fragments.append(courant)
            courant = courant[-_CHEVAUCHEMENT:]
        courant = f"{courant}\n\n{paragraphe}" if courant else paragraphe
    if courant.strip():
        fragments.append(courant)
    return [f.strip() for f in fragments if f.strip()]


def enregistrer_commandes(app: Flask) -> None:
    @app.cli.command("ingerer")
    @click.argument(
        "chemins", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path)
    )
    def ingerer(chemins: tuple[Path, ...]) -> None:
        """Ingère des fichiers (.md, .txt, .html) dans la base de connaissance du copilote."""
        llm = current_app.config["LLM_CLIENT"]
        repository = current_app.config["CONNAISSANCE_REPOSITORY"]
        if repository is None or not llm.embeddings_disponibles:
            raise click.ClickException(
                "Base de connaissance désactivée : configurez EMBED_MODEL (voir .env.example)."
            )
        fichiers = [
            f
            for chemin in chemins
            for f in (sorted(chemin.rglob("*")) if chemin.is_dir() else [chemin])
            if f.is_file() and f.suffix.lower() in {".md", ".txt", ".html", ".htm"}
        ]
        for fichier in fichiers:
            titre, texte = texte_depuis_fichier(fichier)
            fragments = decouper(texte)
            if not fragments:
                continue
            embeddings: list[list[float]] = []
            for i in range(0, len(fragments), _LOT_EMBEDDINGS):
                embeddings.extend(llm.embed(fragments[i : i + _LOT_EMBEDDINGS]))
            repository.remplacer_document(
                fichier.as_posix(), titre, list(zip(fragments, embeddings, strict=True))
            )
            click.echo(f"{fichier} : {len(fragments)} fragment(s) — « {titre} »")
