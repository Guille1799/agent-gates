"""La puerta de la cola segura: sólo abre cuando no hay tanda viva NI trabajo del robot sin fusionar.

Es la pieza (e1) de la decisión `LAS-DOS-COLAS-SE-PISAN` (G, 2026-09-05): «que nadie edite la
cola mientras Ralph corre», garantizado por un cerrojo y no por un acuerdo. La versión en prosa
del acuerdo falló dos veces en una sola noche.

## Lo que se fija, y de dónde sale cada caso

- **Tanda viva → cerrada.** El caso que rompió la noche.
- **Señal rancia → NO bloquea.** Una señal con todos sus pids muertos es lo que quedaba de una
  tanda que murió por el límite de tokens; si bloqueara, la puerta se quedaría cerrada para
  siempre. Se distingue con `pids_muertos_de_la_senal`, la función que el robot escribió esa
  misma noche — la puerta la reutiliza en vez de reinventar la comprobación.
- **Robot con commits sin fusionar → cerrada.** Editar sin ver sus cierres es el tercer fallo de
  aquella noche. Y la puerta NO fusiona: un merge pide juicio.
- **La duda es un NO.** Señal ilegible, señal vacía, git que falla, función de pids ausente:
  cerrada. No haber podido mirar nunca es estar bien.

Todo inyectado: la señal es un fichero de pega, `vive` es un predicado, `corre` es un git de pega.
Así se prueba el rojo sin abrir procesos ni tocar el robot.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent


def _puerta():
    spec = importlib.util.spec_from_file_location(
        "puerta", str(RAIZ / "bin" / "puerta_de_la_cola.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


P = _puerta()


# --- piezas de pega -------------------------------------------------------------------------
def _pids_de_pega(ruta, vive=None):
    """Una `pids_muertos_de_la_senal` mínima y honesta para no importar el tablero en cada test."""
    lineas = [l.strip() for l in Path(ruta).read_text(encoding="utf-8").splitlines() if l.strip()]
    if any(not l.isdigit() for l in lineas):
        return None, "la senal tiene lineas que no son pids"
    pids = []
    for l in lineas:
        if int(l) not in pids:
            pids.append(int(l))
    comprueba = vive if vive is not None else (lambda p: False)
    return [p for p in pids if not comprueba(p)], None


def _git_que_dice(salida, rc=0):
    return lambda args: SimpleNamespace(returncode=rc, stdout=salida, stderr="" if rc == 0 else "fatal: de pega")


SIN_NADA = _git_que_dice("")
DOS_COMMITS = _git_que_dice("abc1234 uno\ndef5678 dos\n")


def _senal(tmp_path, contenido):
    s = tmp_path / ".ralph_active"
    s.write_text(contenido, encoding="utf-8")
    return s


# --- la dirección buena: sí abre --------------------------------------------------------------
def test_sin_senal_y_sin_trabajo_pendiente_ABRE(tmp_path):
    v, motivo = P.se_puede_editar(senal=tmp_path / ".ralph_active", pids_muertos=_pids_de_pega,
                                  corre=SIN_NADA)
    assert v == "pasa", motivo
    assert "ABIERTA" in motivo


def test_una_senal_RANCIA_no_bloquea(tmp_path):
    """Todos sus pids muertos: es lo que deja una tanda que murió. Si bloqueara, para siempre."""
    s = _senal(tmp_path, "111\n222\n")
    v, motivo = P.se_puede_editar(senal=s, vive=lambda p: False, pids_muertos=_pids_de_pega,
                                  corre=SIN_NADA)
    assert v == "pasa", motivo
    assert "rancia" in motivo


# --- los cierres, uno por causa ---------------------------------------------------------------
def test_una_tanda_VIVA_cierra_y_nombra_el_pid(tmp_path):
    s = _senal(tmp_path, "111\n222\n")
    v, motivo = P.se_puede_editar(senal=s, vive=lambda p: p == 222, pids_muertos=_pids_de_pega,
                                  corre=SIN_NADA)
    assert v == "tanda-viva", motivo
    assert "222" in motivo and "111" not in motivo.split("pids")[1].split(")")[0]


def test_trabajo_del_robot_sin_fusionar_cierra_y_dice_cuanto(tmp_path):
    v, motivo = P.se_puede_editar(senal=tmp_path / ".ralph_active", pids_muertos=_pids_de_pega,
                                  corre=DOS_COMMITS)
    assert v == "sin-fusionar", motivo
    assert "2 commit" in motivo and "Fusiona" in motivo


def test_la_tanda_viva_se_mira_ANTES_que_lo_sin_fusionar(tmp_path):
    """Con las dos cosas a la vez, la causa que se nombra es la tanda: es la que no puede esperar."""
    s = _senal(tmp_path, "5\n")
    v, motivo = P.se_puede_editar(senal=s, vive=lambda p: True, pids_muertos=_pids_de_pega,
                                  corre=DOS_COMMITS)
    assert v == "tanda-viva", motivo


# --- la duda es un NO -----------------------------------------------------------------------
def test_una_senal_ILEGIBLE_no_abre(tmp_path):
    s = _senal(tmp_path, "no-soy-un-pid\n")
    v, motivo = P.se_puede_editar(senal=s, pids_muertos=_pids_de_pega, corre=SIN_NADA)
    assert v == "no-se-sabe", motivo


def test_una_senal_VACIA_no_abre(tmp_path):
    s = _senal(tmp_path, "")
    v, motivo = P.se_puede_editar(senal=s, pids_muertos=_pids_de_pega, corre=SIN_NADA)
    assert v == "no-se-sabe", motivo
    assert "vacía" in motivo


def test_si_la_funcion_de_pids_REVIENTA_no_abre(tmp_path):
    s = _senal(tmp_path, "111" + chr(10))
    v, motivo = P.se_puede_editar(senal=s, pids_muertos=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")),
                                  corre=SIN_NADA)
    assert v == "no-se-sabe", motivo


def test_si_la_funcion_de_pids_NO_EXISTE_no_abre(tmp_path, monkeypatch):
    """Si no puede distinguir viva de rancia, no adivina: cierra y dice por qué.

    Es un caso DISTINTO del anterior, y la mutación lo demostró: con el test de «revienta» solo,
    la rama `f is None` nunca se ejecutaba y quitarla no rompía nada. Aquí la función de verdad no
    está —se simula que el tablero no la trae— y la puerta tiene que cerrar igual.
    """
    monkeypatch.setattr(P, "_pids_muertos", lambda: None)
    s = _senal(tmp_path, "111" + chr(10))
    v, motivo = P.se_puede_editar(senal=s, corre=SIN_NADA)
    assert v == "no-se-sabe", motivo
    assert "pids_muertos_de_la_senal" in motivo


def test_si_git_falla_no_abre(tmp_path):
    v, motivo = P.se_puede_editar(senal=tmp_path / ".ralph_active", pids_muertos=_pids_de_pega,
                                  corre=_git_que_dice("", rc=128))
    assert v == "no-se-sabe", motivo
    assert "git" in motivo


def test_una_carpeta_con_el_nombre_de_la_senal_no_abre(tmp_path):
    d = tmp_path / ".ralph_active"
    d.mkdir()
    v, motivo = P.se_puede_editar(senal=d, pids_muertos=_pids_de_pega, corre=SIN_NADA)
    assert v == "no-se-sabe", motivo
    # Se exige el MOTIVO, no solo el veredicto: sin esto, quitar la guarda «es una carpeta»
    # no rompia nada, porque el `except` de mas abajo tambien la cazaba. La mutacion lo
    # destapo: el test pasaba por la razon equivocada.
    assert "no es un fichero" in motivo, motivo


# --- la puerta no toca nada -------------------------------------------------------------------
def test_la_puerta_NO_modifica_la_senal(tmp_path):
    """Es un cerrojo, no una llave. Una señal rancia la limpia `ralph.sh`, no esto."""
    s = _senal(tmp_path, "111\n222\n")
    antes = s.read_bytes()
    P.se_puede_editar(senal=s, vive=lambda p: False, pids_muertos=_pids_de_pega, corre=SIN_NADA)
    assert s.read_bytes() == antes


# --- el exit code, que es lo que un script de fuera lee -----------------------------------------
def test_los_exit_codes_distinguen_las_cuatro_salidas():
    assert P.SALIDA == {"pasa": 0, "no-se-sabe": 2, "tanda-viva": 3, "sin-fusionar": 4}


def test_la_cli_se_puede_ejecutar_y_contesta_con_un_codigo_declarado():
    r = subprocess.run([sys.executable, str(RAIZ / "bin" / "puerta_de_la_cola.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120)
    assert r.returncode in P.SALIDA.values(), (r.stdout, r.stderr)
    assert ("ABIERTA" in r.stdout) == (r.returncode == 0)


def test_la_cli_contesta_con_un_codigo_declarado_TAMBIEN_en_una_consola_cp1252():
    """El fallo real del 2026-09-05: la regresión diaria (consola del Programador, cp1252) corrió este
    mismo test y la CLI reventó con UnicodeEncodeError en el candado (U+1F512), saliendo con 1 — un
    código que NO está declarado. En una terminal UTF-8 nunca se vio. Aquí se fuerza esa consola."""
    entorno = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    r = subprocess.run([sys.executable, str(RAIZ / "bin" / "puerta_de_la_cola.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120, env=entorno)
    assert "UnicodeEncodeError" not in r.stderr, r.stderr[-300:]
    assert r.returncode in P.SALIDA.values(), (r.returncode, r.stdout, r.stderr[-200:])
    assert ("ABIERTA" in r.stdout) == (r.returncode == 0)
