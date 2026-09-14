"""`el-robot-puede-entrar` + `bin/puede_entrar.py` — la pregunta más obvia, y hasta hoy nadie la hacía.

## De dónde sale

MEDIDO la madrugada del 2026-09-13: la casa llevaba **tres noches desautenticada** y ningún rojo lo decía. Las
nocturnas del 11 y del 12 gastaron **10 de 10 iteraciones en 34 y 33 segundos**, y la tanda del robot del 12 a
las 23:00 su única iteración **con 17 tareas en la cola**. Las tres cerraron con «salió con 0».

El `refreshToken` estaba **vacío** mientras `refreshTokenExpiresAt` decía 2026-09-19 — una etiqueta que describe
un token que no está. Sin token de refresco **no hay recuperación automática posible**: hace falta una persona.
Así que lo robusto no era arreglar el refresco, era que la casa se entere el mismo día.

## Los dos casos que más valen

**El campo, nunca el código de salida.** `claude auth status` sale con **0** diciendo `"loggedIn": false`. Un
guion que mirara `$?` concluiría que todo va bien.

**«No he podido preguntar» no es «no».** Un binario ausente o una respuesta ilegible tienen su propia salida.
Si se leyeran como «desautenticado», el aviso saltaría por motivos que no son el suyo — y un aviso que salta
por cualquier cosa se aprende a ignorar.

## Y la asimetría, que va al revés que la del gate

`el_gate_se_cayo_solo.py` ante la duda **revierte**; aquí ante la duda **se sigue**. El lado seguro no es el
mismo: allí absolver de más deja el árbol roto, aquí parar de más cuesta una noche entera de trabajo.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _carga(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, str(ruta))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PE = _carga("puede_entrar_pieza", RAIZ / "bin" / "puede_entrar.py")

SI = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "no-se-imprime@ejemplo"})
NO = json.dumps({"loggedIn": False, "authMethod": "none"})

BUCLE_QUE_PREGUNTA = (
    "#!/usr/bin/env bash\n"
    "set -u\n"
    '$PY bin/puede_entrar.py 2>&1 | tee -a "$RUNLOG"\n'
    "_ENTRA=${PIPESTATUS[0]}\n"
    'if [ "$_ENTRA" -eq 1 ]; then\n'
    '  echo "  NO PUEDE ENTRAR: salgo sin gastar la noche"\n'
    "  exit 5\n"
    "fi\n"
)
BUCLE_QUE_NO_PREGUNTA = "#!/usr/bin/env bash\nset -u\necho 'a trabajar'\n"
BUCLE_QUE_PREGUNTA_Y_LE_DA_IGUAL = (
    # Llama a la pieza y no mira el veredicto: el fichero tiene la palabra correcta y el comportamiento es
    # el de antes. `leccion-el-contrato-solo-no-cierra-la-ruta`.
    "#!/usr/bin/env bash\n"
    "set -u\n"
    "$PY bin/puede_entrar.py || true\n"
    "echo 'a trabajar igual'\n"
)


def _casa(tmp_path, ralph=BUCLE_QUE_PREGUNTA, nocturna=BUCLE_QUE_PREGUNTA):
    r = tmp_path / "casa"
    (r / "scripts").mkdir(parents=True)
    (r / "scripts" / "ralph.sh").write_text(ralph, encoding="utf-8")
    (r / "scripts" / "sesion_nocturna.sh").write_text(nocturna, encoding="utf-8")
    return r


# ── la pieza: se lee el CAMPO ──────────────────────────────────────────────────────────────────────────

def test_loggedIn_true_es_que_SI():
    assert PE.como_esta_la_entrada(SI) == (True, "claude.ai")


def test_loggedIn_false_es_que_NO():
    puede, _ = PE.como_esta_la_entrada(NO)
    assert puede is False


def test_una_CADENA_true_no_cuela_por_true():
    """`d[CAMPO] is True` y no `bool(...)`: la cadena "false" también es verdadera para bool()."""
    puede, _ = PE.como_esta_la_entrada(json.dumps({"loggedIn": "false"}))
    assert puede is False, "una cadena no es un booleano"


def test_una_respuesta_que_no_es_JSON_es_NO_SE_PUDO_PREGUNTAR():
    puede, motivo = PE.como_esta_la_entrada("Error: something went wrong")
    assert puede is None and "JSON" in motivo


def test_un_JSON_sin_el_campo_es_NO_SE_PUDO_PREGUNTAR():
    puede, motivo = PE.como_esta_la_entrada(json.dumps({"apiProvider": "firstParty"}))
    assert puede is None and "loggedIn" in motivo


def test_un_binario_que_no_existe_es_NO_SE_PUDO_PREGUNTAR(tmp_path):
    puede, _ = PE.como_esta_la_entrada(binario=str(tmp_path / "no_existe.exe"))
    assert puede is None


def test_el_correo_NO_sale_en_el_detalle():
    """Esto acaba en logs de cada noche: un tablero no imprime identidades."""
    _, detalle = PE.como_esta_la_entrada(SI)
    assert "@" not in str(detalle), detalle


# ── los tres códigos de salida de la pieza ─────────────────────────────────────────────────────────────

def test_los_tres_codigos():
    assert PE.main(["--salida", SI]) == 0
    assert PE.main(["--salida", NO]) == 1
    assert PE.main(["--salida", "no soy json"]) == 2


# ── el comprobador ─────────────────────────────────────────────────────────────────────────────────────

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
