"""La pregunta que evita borrar trabajo ajeno: contesta los tres códigos, y el 0 solo si de verdad.

Los tres casos importan por separado, y el tercero es el que suele faltar:

    0  HEAD es tu commit                    → deshacer es seguro
    1  la rama se movió                     → NO deshagas
    2  no se pudo mirar                     → NO deshagas

🔑 El test que más vale es el de que un **0 no se pueda colar**: si esta herramienta contesta
«puedes borrar» cuando no ha podido comprobar, hace exactamente el daño que existe para evitar.
Y el daño es invisible — el commit de otro desaparece sin rastro.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import el_commit_sigue_siendo_mio as pieza  # noqa: E402  (conftest pone bin/ en el path)


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, f"git {' '.join(args)} -> {r.returncode}: {r.stderr}"
    return r.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Un repositorio de verdad con un commit. Nada de simulacros: la pieza habla con git."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", ".")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("base\n", encoding="utf-8")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _commit(repo: Path, texto: str) -> str:
    (repo / f"{texto}.txt").write_text(texto + "\n", encoding="utf-8")
    _git(repo, "add", f"{texto}.txt")
    _git(repo, "commit", "-q", "-m", texto)
    return _git(repo, "rev-parse", "HEAD")


def test_si_HEAD_es_tu_commit_deshacer_es_seguro(repo, capsys):
    mio = _commit(repo, "mio")
    assert pieza.main([mio, "--repo", str(repo)]) == 0
    assert "SIGUE SIENDO TUYO" in capsys.readouterr().out


def test_si_alguien_commiteo_despues_NO_se_deshace(repo, capsys):
    """El caso real: tres veces en un día se borró trabajo que cayó en esta ventana."""
    mio = _commit(repo, "mio")
    _commit(repo, "de_otra_sesion")
    assert pieza.main([mio, "--repo", str(repo)]) == 1
    salida = capsys.readouterr().out
    assert "NO ES TUYO" in salida
    assert "1 commit(s) de otro en medio" in salida
    assert "de_otra_sesion" in salida, "tiene que decir QUÉ hay en medio, no solo que hay algo"


def test_si_no_hay_repo_contesta_2_y_NO_autoriza(capsys, tmp_path):
    """Un «no se pudo mirar» jamás se traduce en «puedes borrar»."""
    assert pieza.main(["abc123", "--repo", str(tmp_path / "no_existe")]) == 2
    assert "NO SE PUDO SABER" in capsys.readouterr().out


def test_si_el_directorio_no_es_un_repo_contesta_2(tmp_path, capsys):
    """Existe la carpeta pero no hay git dentro: sigue siendo 2, no 0."""
    (tmp_path / "vacia").mkdir()
    assert pieza.main(["abc123", "--repo", str(tmp_path / "vacia")]) == 2
    assert "NO SE PUDO SABER" in capsys.readouterr().out


def test_sin_sha_contesta_2(repo, capsys):
    """Llamarla mal no puede dar permiso para borrar."""
    assert pieza.main(["   ", "--repo", str(repo)]) == 2
    assert "NO SE PUDO SABER" in capsys.readouterr().out


def test_un_sha_que_no_existe_en_la_historia_NO_autoriza(repo, capsys):
    """Un sha inventado no es HEAD, así que la respuesta es 1 — y sin reventar."""
    _commit(repo, "mio")
    assert pieza.main(["0" * 40, "--repo", str(repo)]) == 1
    assert "NO ES TUYO" in capsys.readouterr().out


def test_ningun_camino_devuelve_0_sin_haber_leido_HEAD(monkeypatch, repo):
    """La trampa prohibida, fijada: si no se pudo leer HEAD, NUNCA es 0.

    Se fuerza el fallo de la lectura en vez de esperar a que ocurra. Sin esto, un cambio futuro
    que trate el «no sé» como «sí» pasaría todos los demás tests.
    """
    monkeypatch.setattr(pieza, "head_de", lambda _repo: None)
    assert pieza.main(["cualquiera", "--repo", str(repo)]) == 2
