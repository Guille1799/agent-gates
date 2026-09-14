# -*- coding: utf-8 -*-
"""La puerta de la cola segura: la única forma legítima de escribir en ella.

## Por qué existe (decisión de G, 2026-09-05: «la e), la puerta con cerrojo»)

La noche del 2026-09-05 el robot y la sesión madre cerraron **la misma tarea dos veces**, con dos
versiones distintas del mismo comprobador, y otra vez con la siguiente. No fue despiste: el robot
lee la cola una vez al arrancar la tanda y trabaja horas sobre esa foto; la madre edita `main` en
vivo. Ninguno ve al otro. Y hay un TERCER escritor, `encolar_fallo.py`, que escribe desde el
healthcheck a cualquier hora.

La regla, en palabras de G: **«que nadie edite la cola mientras Ralph corre»**. Y eso no lo
garantiza un acuerdo —la versión en prosa ya falló dos veces en una noche— sino un mecanismo por
el que hay que pasar.

## Qué hace, y qué NO hace

Contesta UNA pregunta: *¿se puede editar la sección segura ahora?* Y sólo dice sí cuando las dos
condiciones se cumplen a la vez:

1. **No hay ninguna tanda viva.** Se lee `.ralph_active` del worktree del robot —la señal que
   `ralph.sh` ya escribe— y se distingue *viva* de *rancia* con `pids_muertos_de_la_senal`, la
   función que el propio robot escribió esa noche. Sin esa distinción, una señal que se quedó de
   una tanda muerta bloquearía la puerta para siempre.
2. **El robot no tiene trabajo sin fusionar.** Si `ralph/auto` va por delante de `main`, la madre
   estaría editando sin ver lo que el robot cerró, que es exactamente el tercer fallo de aquella
   noche. La puerta no fusiona —un merge puede tener conflictos y eso pide juicio—: se niega y
   dice qué hay que fusionar.

**Y la duda se resuelve como NO.** Si la señal no se puede leer, si git falla, si la función de
pids no está: cerrado. No haber podido mirar nunca es estar bien.

Lo que NO hace: no edita nada, no borra la señal, no toca al robot. Es un cerrojo, no una llave.

## Cómo se usa

    venv/Scripts/python.exe bin/puerta_de_la_cola.py      # exit 0 = pasa · 3 = tanda viva
                                                          # 4 = robot sin fusionar · 2 = no se sabe

O desde Python, antes de escribir en la cola: `ok, motivo = se_puede_editar()`.

## Sus límites, dichos

La puerta se puede saltar editando el markdown a mano. Por eso existe la pieza (e3): un
comprobador que denuncia una ficha con distinta casilla en `main` y en `ralph/auto`. La puerta
hace imposible el choque para quien pasa por ella; el comprobador ve a quien no pasó.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Donde viven los árboles. Declarado, no deducido de `RAIZ`: en un worktree `RAIZ.parent` es
#: `.claude/worktrees/`, donde no vive ningún robot (medido el 2026-09-04). Es la misma
#: declaración que `_RAIZ_PROYECTOS` en `scripts/aceptacion.py`.
RAIZ_PROYECTOS = Path(os.environ.get("PROYECTOS_RAIZ") or Path.home() / "proyectos")
SENAL_DEL_ROBOT = RAIZ_PROYECTOS / "mcp-ralph" / ".ralph_active"
RAMA_DEL_ROBOT = "ralph/auto"

SALIDA = {"pasa": 0, "no-se-sabe": 2, "tanda-viva": 3, "sin-fusionar": 4}


def _pids_muertos():
    """La función del tablero, importada sólo cuando hace falta (el fichero pesa 300 KB)."""
    import importlib.util
    ruta = RAIZ / "scripts" / "aceptacion.py"
    if not ruta.is_file():
        return None
    spec = importlib.util.spec_from_file_location("tablero_para_la_puerta", str(ruta))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "pids_muertos_de_la_senal", None)


def tanda_viva(senal=None, vive=None, pids_muertos=None):
    """¿Hay un Ralph corriendo? Devuelve `(estado, motivo)`.

    `estado` es `"viva"`, `"rancia"` (la señal existe pero todos sus pids han muerto), `"ausente"`
    o `None` cuando no se puede saber. `vive` y `pids_muertos` son inyectables para poder probar
    que sabe decir que no sin abrir procesos de verdad.
    """
    s = Path(senal) if senal is not None else SENAL_DEL_ROBOT
    if not s.exists():
        return "ausente", "no hay señal en " + str(s)
    if not s.is_file():
        return None, str(s) + " existe y no es un fichero"
    f = pids_muertos if pids_muertos is not None else _pids_muertos()
    if f is None:
        return None, ("no se puede distinguir una señal viva de una rancia: falta "
                      "`pids_muertos_de_la_senal`, y sin eso la duda es un no")
    try:
        texto = s.read_text(encoding="utf-8", errors="replace")
        escritos = sorted({int(l.strip()) for l in texto.splitlines() if l.strip().isdigit()})
        muertos, motivo = f(s, vive=vive) if vive is not None else f(s)
    except Exception as e:
        return None, "la señal no se pudo leer: " + type(e).__name__ + ": " + str(e)[:60]
    if motivo:
        return None, "la señal no tiene forma de señal: " + str(motivo)
    if not escritos:
        return None, "la señal existe y está vacía: no se sabe si hay tanda"
    vivos = [p for p in escritos if p not in set(muertos or ())]
    if vivos:
        return "viva", "hay una tanda viva (pids " + ", ".join(map(str, vivos)) + ")"
    return "rancia", ("la señal es rancia: todos sus pids han muerto (" + ", ".join(map(str, escritos))
                      + "). No bloquea; la limpieza es de `ralph.sh`")


def robot_sin_fusionar(repo=None, rama=RAMA_DEL_ROBOT, corre=None):
    """Commits de la rama del robot que `main` no tiene. `(n, motivo)`; `n` es None si git falla."""
    r = Path(repo) if repo is not None else RAIZ
    ejecuta = corre or (lambda args: subprocess.run(
        ["git", "-C", str(r), *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60))
    try:
        p = ejecuta(["log", "--oneline", "main.." + rama])
    except Exception as e:
        return None, "git no contestó: " + type(e).__name__ + ": " + str(e)[:60]
    if p.returncode != 0:
        return None, "git falló al mirar main.." + rama + ": " + (p.stderr or "").strip()[:80]
    lineas = [l for l in (p.stdout or "").splitlines() if l.strip()]
    return len(lineas), (str(len(lineas)) + " commit(s) del robot sin fusionar" if lineas
                         else "el robot no tiene nada sin fusionar")


def se_puede_editar(senal=None, repo=None, rama=RAMA_DEL_ROBOT, vive=None, pids_muertos=None,
                    corre=None):
    """La pregunta entera. Devuelve `(veredicto, motivo)` con `veredicto` una clave de `SALIDA`."""
    estado, m1 = tanda_viva(senal, vive=vive, pids_muertos=pids_muertos)
    if estado is None:
        return "no-se-sabe", "CERRADA — " + m1
    if estado == "viva":
        return "tanda-viva", "CERRADA — " + m1 + ". Espera a que termine; su cola es una foto y no vería lo que escribas"
    n, m2 = robot_sin_fusionar(repo, rama, corre=corre)
    if n is None:
        return "no-se-sabe", "CERRADA — " + m2
    if n > 0:
        return "sin-fusionar", ("CERRADA — " + m2 + ". Fusiona `" + rama + "` antes de tocar la cola,"
                                " o editarás sin ver lo que el robot cerró")
    return "pasa", "ABIERTA — " + m1 + "; " + m2


def main(argv=None):
    # La consola del Programador de tareas es cp1252, y el candado (U+1F512) no cabe: la CLI
    # reventaba con UnicodeEncodeError y salia con 1, un codigo que NO esta declarado. Lo destapo
    # la regresion diaria el 2026-09-05 — en una terminal UTF-8 nunca se vio. Un cerrojo que se
    # cae al hablar no es un cerrojo: la salida se fija a UTF-8 y lo que no quepa se reemplaza.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    veredicto, motivo = se_puede_editar()
    print(("✅ " if veredicto == "pasa" else "🔒 ") + motivo)
    return SALIDA[veredicto]


if __name__ == "__main__":
    sys.exit(main())
