"""Trabajo que sólo existe fuera de la rama principal: se encuentra, y un «no sé» no es un «sí».

Los tres códigos importan por separado, y el tercero es el que suele faltar:

    0  todo lo de fuera está también en la rama   → limpiar es seguro
    1  hay algo que sólo existe fuera             → míralo antes de borrar
    2  no se pudo mirar                           → no limpies

🔑 El test que más vale es `test_un_fichero_sin_linea_distintiva_NO_se_da_por_salvado`. La primera
versión de esta comprobación hacía un `continue` silencioso ahí: cualquier fichero de líneas
cortas se daba por salvado **sin mirar nada**, que es el tercer estado colapsado en verde. Lo cazó
su propia mutación, y este test lo fija para que no vuelva.

Y el segundo que más vale es `test_un_rescate_RENOMBRADO_cuenta_como_a_salvo`: sin él, la
comparación por ruta dejaría en rojo para siempre un trabajo ya rescatado, y un rojo que no se
puede apagar enseña a ignorar los rojos.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import nada_vive_solo_fuera_de_main as pieza  # noqa: E402  (conftest pone bin/ en el path)

DISTINTIVA = "# ATAQUE 3 - falsos positivos por subcadena de un termino corto"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, f"git {' '.join(args)} -> {r.returncode}: {r.stderr}"
    return r.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Un repositorio de verdad con `main` y un commit. Nada de simulacros: habla con git."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main", ".")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("base\n", encoding="utf-8")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _rama_muerta(repo: Path, nombre: str, fichero: str, contenido: str) -> None:
    """Crea una rama, commitea un fichero, vuelve a main y BORRA la rama.

    Así el commit queda vivo sólo por el reflog — que es exactamente la situación real: la rama
    `prueba/auditor` del caso de 2026-09-16 ya no existía.
    """
    _git(repo, "checkout", "-q", "-b", nombre)
    (repo / fichero).parent.mkdir(parents=True, exist_ok=True)
    (repo / fichero).write_text(contenido, encoding="utf-8")
    _git(repo, "add", fichero)
    _git(repo, "commit", "-q", "-m", "trabajo en " + nombre)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "-q", "-D", nombre)


def test_un_fichero_que_solo_existe_fuera_se_encuentra(repo, capsys):
    """El caso real: dos ficheros vivos sólo en un commit de una rama ya borrada."""
    _rama_muerta(repo, "prueba", "casos/ataque.md", DISTINTIVA + "\n\n- AI\n- ETL\n")
    assert pieza.main(["--repo", str(repo)]) == 1
    salida = capsys.readouterr().out
    assert "SOLO EXISTEN FUERA" in salida
    assert "casos/ataque.md" in salida, "tiene que decir CUAL, no solo que hay algo"


def test_un_rescate_RENOMBRADO_cuenta_como_a_salvo(repo, capsys):
    """Se compara el CONTENIDO, no la ruta: un rescate cambia el nombre y añade cabecera."""
    _rama_muerta(repo, "prueba", "casos/ataque.md", DISTINTIVA + "\n\n- AI\n")
    salvado = repo / "tests" / "rescatado_con_otro_nombre.md"
    salvado.parent.mkdir(parents=True, exist_ok=True)
    salvado.write_text("<!-- rescatado de una rama muerta -->\n\n" + DISTINTIVA + "\n\n- AI\n",
                       encoding="utf-8")
    _git(repo, "add", "tests")
    _git(repo, "commit", "-q", "-m", "rescate")

    assert pieza.main(["--repo", str(repo)]) == 0
    assert "NADA VIVE SOLO FUERA" in capsys.readouterr().out


def test_un_fichero_sin_linea_distintiva_NO_se_da_por_salvado(repo, capsys):
    """🔴 La trampa prohibida, fijada: «no pude comprobarlo» jamás es «está a salvo».

    Un fichero cuyas líneas son todas cortas no se puede buscar. La primera versión lo saltaba en
    silencio y devolvía 0.
    """
    _rama_muerta(repo, "prueba", "t2.md", "x\n")
    assert pieza.main(["--repo", str(repo)]) == 1
    salida = capsys.readouterr().out
    assert "NO SE PUDO COMPROBAR" in salida
    assert "t2.md" in salida
    assert "esta a salvo" in salida, "tiene que decir explicitamente que NO es un aprobado"


def test_lo_declarado_ACEPTADO_no_cuenta(repo, capsys):
    """Un temporal que se regenera no es trabajo perdido, pero se declara por escrito."""
    _rama_muerta(repo, "prueba", "tmp_volcado.json", '{"a": 1}\n')
    assert pieza.main(["--repo", str(repo), "--acepta", "tmp_volcado.json"]) == 0


def test_lo_que_YA_esta_en_main_no_cuenta(repo, capsys):
    """Un commit fuera de main que no aporta ficheros nuevos no es trabajo escondido."""
    _rama_muerta(repo, "prueba", "a.txt", "base\ncambio que luego se tiro\n")
    assert pieza.main(["--repo", str(repo)]) == 0


def test_sin_repo_contesta_2_y_NO_autoriza(tmp_path, capsys):
    assert pieza.main(["--repo", str(tmp_path / "no_existe")]) == 2
    assert "NO SE PUDO SABER" in capsys.readouterr().out


def test_si_la_rama_no_existe_contesta_2(repo, capsys):
    """Preguntar por una rama que no está no es «todo limpio»."""
    assert pieza.main(["--repo", str(repo), "--rama", "trunk"]) == 2
    assert "NO SE PUDO SABER" in capsys.readouterr().out


def test_ningun_camino_devuelve_0_sin_haber_podido_enumerar(monkeypatch, repo, capsys):
    """Si no se pudo ni empezar, es 2. Sin esto, un cambio futuro que trate el «no sé» como
    «no hay nada» pasaría todos los demás tests."""
    monkeypatch.setattr(pieza, "fuera_de", lambda *_a, **_k: None)
    assert pieza.main(["--repo", str(repo)]) == 2
