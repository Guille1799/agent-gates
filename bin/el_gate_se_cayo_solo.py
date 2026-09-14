#!/usr/bin/env python3
"""¿El gate falló por el commit del agente, o se cayó solo? — la pregunta que decide si se revierte.

    <py> bin/el_gate_se_cayo_solo.py <log-del-gate> [--py <interprete>] [--tope N]

    exit 0 → SE CAYÓ SOLO: los mismos tests vuelven a pasar. **No revertir.**
    exit 1 → fue el commit: al menos uno sigue rojo. **Revertir.**
    exit 2 → NO SE PUDO SABER: no hay líneas `FAILED` que releer. **Revertir.**
    exit 3 → demasiados fallos para ser inestabilidad. **Revertir.**

## Por qué existe, y tiene fecha

El 2026-09-12 la sesión nocturna corrió por primera vez, hizo su tarea entera, la commiteó, y **su propio bucle
se la tiró**: el gate re-verificado falló en `tests/test_add_embeddings.py::test_merge_insert_idempotent_under_race`
con un error del sistema operativo —LanceDB, «Failed to create temp dir … The system cannot find the path
specified», os error 3— que no tenía **nada** que ver con lo que ella había tocado, que eran dos ficheros de
`auditoria/`. El mismo test pasó a mano ese mismo día en 4,8 s. El trabajo se rescató con un `cherry-pick` sobre
un commit que seguía colgando, y además lo conservaba la rama del robot, que había sincronizado seis minutos antes.

La reversión hizo **exactamente lo que debe**: un agente no puede dejar el árbol roto. El problema es que no sabía
distinguir *«tu commit rompió el gate»* de *«el gate se cayó solo»*, y ante la duda tiraba trabajo bueno.

## Por qué re-correr y no clasificar el error por su texto

La otra opción era una lista de mensajes que «no cuentan» (errores de disco, de red, de permisos). Se descartó: una
lista de excepciones caduca el día que aparece un error nuevo, y mientras tanto se lee como cobertura. Re-correr no
necesita saber qué salió mal — pregunta a la realidad otra vez, que es lo único que no caduca.

## Y los tres casos en los que se niega a absolver

**No poder saber no es absolver.** Si el gate falló sin dejar líneas `FAILED` que releer (un error de sintaxis, un
fallo al recolectar, un timeout, o un gate compuesto que reventó en su segunda mitad), esto sale con 2 y el bucle
revierte igual. Y si fallaron **más de `--tope`** tests, tampoco: eso ya no tiene forma de inestabilidad, tiene
forma de haber roto algo. El sesgo es deliberado y va en la dirección segura: se absuelve poco, y solo con prueba.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
#: Más de estos y no es inestabilidad: es un cambio que rompió cosas. El número es pequeño a propósito.
TOPE_DE_FALLOS = 5
#: Un re-pase tiene que ser corto. Si tarda más que esto, el bucle no puede esperarlo cada noche.
TOPE_SEGUNDOS = 600
#: `FAILED ruta::test - mensaje` es la forma con la que pytest resume al final. Se corta en el ` - `.
_FALLADO = re.compile(r"^FAILED\s+(\S+?)(?:\s+-\s+.*)?$", re.M)


def tests_que_fallaron(texto: str) -> list[str]:
    """Los identificadores de test que pytest resumió como FAILED, sin repetir y en orden."""
    fuera, vistos = [], set()
    for nodo in _FALLADO.findall(texto):
        if nodo not in vistos:
            vistos.add(nodo)
            fuera.append(nodo)
    return fuera


def vuelven_a_pasar(nodos: list[str], py: str, raiz: Path, tope_s: int = TOPE_SEGUNDOS):
    """(pasan, detalle). `pasan` es None si no se pudo volver a correr — y eso NO es absolver."""
    if not nodos:
        return None, "no hay tests que releer"
    try:
        r = subprocess.run([py, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider"],
                           cwd=str(raiz), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=tope_s)
    except subprocess.TimeoutExpired:
        return None, "el re-pase tardo mas de " + str(tope_s) + " s"
    except OSError as e:
        return None, "no se pudo lanzar el re-pase: " + type(e).__name__
    ultima = (r.stdout or "").strip().split("\n")[-1][:120] if r.stdout else ""
    return r.returncode == 0, ultima


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="el gate fallo: fue el commit o se cayo solo?")
    p.add_argument("log", help="el fichero donde el bucle guardo la salida del gate")
    p.add_argument("--py", default=None, help="interprete con el que re-correr (por defecto, el venv de la raiz)")
    p.add_argument("--raiz", default=None)
    p.add_argument("--tope", type=int, default=TOPE_DE_FALLOS)
    p.add_argument("--tope-segundos", type=int, default=TOPE_SEGUNDOS)
    a = p.parse_args(argv)

    raiz = Path(a.raiz) if a.raiz else _RAIZ
    py = a.py or str(raiz / "venv" / "Scripts" / "python.exe")
    ruta = Path(a.log)
    if not ruta.is_file():
        print("no se pudo saber: no existe el log del gate " + str(ruta), file=sys.stderr)
        return 2

    nodos = tests_que_fallaron(ruta.read_text("utf-8", errors="replace"))
    if not nodos:
        print("no se pudo saber: el gate fallo sin dejar lineas FAILED que releer (¿error de sintaxis, de"
              " recoleccion, un timeout, o la otra mitad de un gate compuesto?). Se revierte.", file=sys.stderr)
        return 2
    if len(nodos) > a.tope:
        print("no es inestabilidad: fallaron " + str(len(nodos)) + " tests (tope " + str(a.tope)
              + "). Eso tiene forma de haber roto algo. Se revierte.", file=sys.stderr)
        return 3

    pasan, detalle = vuelven_a_pasar(nodos, py, raiz, a.tope_segundos)
    if pasan is None:
        print("no se pudo saber: " + str(detalle) + ". Se revierte.", file=sys.stderr)
        return 2
    if pasan:
        print("EL GATE SE CAYO SOLO: los " + str(len(nodos)) + " test(s) que fallaron vuelven a pasar al"
              " re-correrlos, asi que el commit no los rompio. NO se revierte.", file=sys.stderr)
        for n in nodos:
            print("   · " + n, file=sys.stderr)
        print("   " + str(detalle), file=sys.stderr)
        return 0
    print("fue el commit: al menos uno de los " + str(len(nodos)) + " sigue rojo al re-correrlo. Se revierte.",
          file=sys.stderr)
    print("   " + str(detalle), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
