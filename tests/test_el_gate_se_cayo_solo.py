"""`bin/el_gate_se_cayo_solo.py` (ficha UN-TEST-INESTABLE-TIRA-EL-TRABAJO-DEL-AGENTE, 2026-09-12): antes de
revertir el trabajo de un agente, se pregunta si el gate falló por su commit o se cayó solo.

## De dónde sale, y tiene fecha

El 2026-09-12 la sesión nocturna corrió por primera vez, hizo su tarea entera, la commiteó, y **su propio bucle
se la tiró**: el gate re-verificado falló en un test de LanceDB con un error del sistema operativo («Failed to
create temp dir … os error 3») que no tenía nada que ver con lo que ella había tocado, que eran dos ficheros de
`auditoria/`. El mismo test pasó a mano ese día en 4,8 s.

La reversión hizo lo que debe. Lo que no sabía es distinguir «tu commit rompió el gate» de «el gate se cayó solo»,
y ante la duda tiraba trabajo bueno.

## Por qué los casos están sesgados hacia revertir

De los ocho casos de la pieza, **cuatro comprueban que NO absuelve**. Eso es deliberado: absolver de más deja el
árbol roto, que es exactamente lo que la reversión existe para impedir. **No poder saber no es absolver**, y hay
tres formas de no poder saber: sin líneas `FAILED` que releer, demasiados fallos para ser inestabilidad, y un
re-pase que no se pudo ejecutar.

## Y las dos mitades del fichero

Los ocho primeros tests miden **la pieza**. Los siete últimos miden **al que la mide** —
`el-gate-caido-no-tira-trabajo-bueno`, en el tablero — inyectándole casas de pega, porque la ronda de cada mañana
corre `scripts/aceptacion.py` y no corre pytest: si alguien saca la pregunta de un bucle, el comprobador es lo
único que lo canta al día siguiente. Un comprobador sin observador es media pieza.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _pieza():
    spec = importlib.util.spec_from_file_location("el_gate_se_cayo_solo", str(RAIZ / "bin" / "el_gate_se_cayo_solo.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["el_gate_se_cayo_solo"] = mod
    spec.loader.exec_module(mod)
    return mod


G = _pieza()

LOG_CON_UN_FALLO = """\
tests/test_uno.py .F
=========================== short test summary info ===========================
FAILED tests/test_add_embeddings.py::test_merge_insert_idempotent_under_race - RuntimeError: lance error
1 failed, 1650 passed, 1 skipped in 445.89s
"""


def _log(tmp_path, texto, nombre="gate.log"):
    p = tmp_path / nombre
    p.write_text(texto, encoding="utf-8")
    return p


def _proyecto(tmp_path, cuerpos: dict):
    """Un proyectito con tests de pega, para que el re-pase tenga algo real que correr."""
    r = tmp_path / "proy"
    (r / "tests").mkdir(parents=True)
    for nombre, cuerpo in cuerpos.items():
        (r / "tests" / nombre).write_text(cuerpo, encoding="utf-8")
    return r


# --- leer lo que pytest resumió ---------------------------------------------------------------------------

def test_saca_el_identificador_del_test_que_fallo():
    n = G.tests_que_fallaron(LOG_CON_UN_FALLO)
    assert n == ["tests/test_add_embeddings.py::test_merge_insert_idempotent_under_race"], n


def test_no_repite_el_mismo_test_dos_veces():
    doble = LOG_CON_UN_FALLO + LOG_CON_UN_FALLO
    assert len(G.tests_que_fallaron(doble)) == 1


def test_un_log_sin_lineas_FAILED_no_da_ninguno():
    assert G.tests_que_fallaron("ERROR collecting tests/x.py\n!!! Interrupted: 3 errors !!!\n") == []


# --- el verde, que es el caso por el que existe ------------------------------------------------------------

def test_si_el_test_VUELVE_A_PASAR_sale_0_y_no_se_revierte(tmp_path):
    proy = _proyecto(tmp_path, {"test_inestable.py": "def test_va():\n    assert True\n"})
    log = _log(tmp_path, "FAILED tests/test_inestable.py::test_va - OSError: temp dir\n")
    rc = G.main([str(log), "--py", sys.executable, "--raiz", str(proy)])
    assert rc == 0, rc


# --- los cuatro casos en los que NO absuelve ---------------------------------------------------------------

def test_si_SIGUE_FALLANDO_sale_1_y_se_revierte(tmp_path):
    proy = _proyecto(tmp_path, {"test_roto.py": "def test_no_va():\n    assert False\n"})
    log = _log(tmp_path, "FAILED tests/test_roto.py::test_no_va - AssertionError\n")
    assert G.main([str(log), "--py", sys.executable, "--raiz", str(proy)]) == 1


def test_sin_lineas_FAILED_es_NO_SE_PUDO_SABER_y_se_revierte(tmp_path):
    """Un error de sintaxis, un fallo al recolectar, un timeout, o la otra mitad de un gate compuesto."""
    log = _log(tmp_path, "ERROR collecting tests/x.py\n!!! Interrupted: 57 errors during collection !!!\n")
    assert G.main([str(log), "--py", sys.executable, "--raiz", str(tmp_path)]) == 2


def test_DEMASIADOS_fallos_no_es_inestabilidad_y_se_revierte(tmp_path):
    """Seis tests rojos tienen forma de haber roto algo, no de un temporal que desapareció."""
    muchos = "".join("FAILED tests/t.py::test_%d - x\n" % i for i in range(6))
    log = _log(tmp_path, muchos)
    assert G.main([str(log), "--py", sys.executable, "--raiz", str(tmp_path), "--tope", "5"]) == 3


def test_un_log_que_no_existe_es_NO_SE_PUDO_SABER(tmp_path):
    assert G.main([str(tmp_path / "no_existe.log")]) == 2


def test_un_interprete_que_no_arranca_es_NO_SE_PUDO_SABER_no_absolucion(tmp_path):
    """Si el re-pase no se puede ejecutar, se revierte. No poder medir no es estar bien."""
    proy = _proyecto(tmp_path, {"test_x.py": "def test_x():\n    assert True\n"})
    log = _log(tmp_path, "FAILED tests/test_x.py::test_x - x\n")
    assert G.main([str(log), "--py", str(tmp_path / "no_existe.exe"), "--raiz", str(proy)]) == 2
# ----------------------------------------------------------------------------------------------------------
# RECORTE DECLARADO (agent-gates, 2026-09-14)
#
# Aqui abajo, en el repo de origen, venia la OTRA MITAD del test: la que carga
# `scripts/aceptacion.py` y comprueba que esta pieza ademas esta ENCHUFADA a la ronda de
# cada manana -que corre el arnes, no pytest-. Esa mitad no se puede traer sin traerse el
# arnes entero (10.260 lineas que hablan de un repo privado), asi que se ha quitado.
#
# Lo que queda prueba LA HERRAMIENTA. Lo que falta probaba QUE ALGUIEN LA LLAMA.
# Y esa segunda mitad existe por un fallo medido el 2026-09-05: una pieza que existia,
# pasaba su contrato, y no la llamaba nadie. Se dice aqui para que la ausencia sea una
# decision declarada y no un hueco silencioso.
# ----------------------------------------------------------------------------------------------------------
# Y con el mismo motivo se ha quitado `test_LOS_DOS_BUCLES_preguntan_antes_de_revertir`, que leia
# `scripts/ralph.sh` para comprobar que los DOS bucles preguntan antes de revertir. El bucle no
# viaja: lleva rutas de una maquina concreta.
