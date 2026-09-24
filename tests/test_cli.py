import httpx
import respx

from logiflow_ai_service.app import create_app
from logiflow_ai_service.cli import decouper, texte_depuis_fichier
from tests.fakes import ConnaissanceRepositoryMemoire


def test_decouper_respecte_la_taille_et_conserve_le_texte():
    paragraphes = [f"Paragraphe {i} " + "x" * 400 for i in range(20)]
    fragments = decouper("\n\n".join(paragraphes))

    assert len(fragments) > 1
    assert all(len(f) <= 3300 for f in fragments)
    assert all(any(f"Paragraphe {i} " in f for f in fragments) for i in range(20))


def test_texte_depuis_html(tmp_path):
    fichier = tmp_path / "guide.html"
    fichier.write_text(
        "<html><head><title>Guide LogiFlow</title><style>p{}</style></head>"
        "<body><h1>Dossiers</h1><p>Créer un dossier &amp; le valider.</p></body></html>",
        encoding="utf-8",
    )
    titre, texte = texte_depuis_fichier(fichier)

    assert titre == "Guide LogiFlow"
    assert "Créer un dossier & le valider." in texte
    assert "p{}" not in texte


def test_commande_ingerer(settings, repository, tmp_path):
    connaissance = ConnaissanceRepositoryMemoire()
    app = create_app(
        settings.model_copy(update={"embed_model": "modele-embed"}),
        conversation_repository=repository,
        connaissance_repository=connaissance,
    )
    (tmp_path / "procedure.md").write_text("# Procédure ADR\n\nContenu.", encoding="utf-8")

    with respx.mock() as mock:
        mock.post(f"{settings.llm_base_url}/embeddings").mock(
            return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5] * 8}]})
        )
        resultat = app.test_cli_runner().invoke(args=["ingerer", str(tmp_path)])

    assert resultat.exit_code == 0, resultat.output
    [(titre, fragments)] = connaissance.documents.values()
    assert titre == "Procédure ADR"
    assert fragments[0][0].startswith("# Procédure ADR")


def test_ingerer_sans_modele_d_embeddings_est_refuse(settings, repository, tmp_path):
    app = create_app(settings, conversation_repository=repository)
    (tmp_path / "a.md").write_text("# A", encoding="utf-8")

    resultat = app.test_cli_runner().invoke(args=["ingerer", str(tmp_path)])

    assert resultat.exit_code != 0
    assert "EMBED_MODEL" in resultat.output
