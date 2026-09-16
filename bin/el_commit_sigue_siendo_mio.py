#!/usr/bin/env python3
"""¿Sigue siendo mío el último commit? — la pregunta que hay que hacer ANTES de deshacer nada.

    <py> bin/el_commit_sigue_siendo_mio.py <sha-que-hice-yo> [--repo RUTA]

    exit 0 → SÍ: HEAD es exactamente tu commit. **Deshacer es seguro.**
    exit 1 → NO: la rama se movió, hay commits de otro en medio. **NO deshagas.**
    exit 2 → NO SE PUDO SABER: no hay repo, o git no contesta. **NO deshagas.**

## Por qué existe, y tiene fecha

Un agente que programa solo necesita poder deshacer su propio trabajo: si su cambio rompe la
suite, el árbol no puede quedarse roto. El patrón obvio es guardar `HEAD` al empezar y, si el
gate falla, `git reset --hard` a ese punto.

**Y ese patrón destruyó trabajo ajeno tres veces en un solo día** (2026-08-24). El motivo es una
ventana de tiempo que no se ve al escribirlo: entre guardar `HEAD` y decidir el reset pasan
**minutos** —se ejecuta el agente, la suite entera, las comprobaciones de aceptación—. Cualquier
commit que otra persona o otro proceso haga en esa ventana queda **entre** los dos puntos, y el
reset se lo lleva por delante sin decir nada.

Sobrevivió porque estaba empujado a un remoto, o sea **por costumbre, no por diseño**.

## La asimetría, y es deliberada

Los tres códigos de salida se reparten **dos a uno contra deshacer**: solo el 0 autoriza.

🔑 **Porque los dos errores no cuestan lo mismo.** Dejar un commit malo del agente es visible: la
suite sigue roja, alguien lo ve por la mañana y lo arregla. Borrar el commit de otro es
**invisible**: no queda rastro, nadie sabe que existió, y quien lo escribió descubre días después
que su trabajo no está. Ante la duda, no se borra.

## Por qué esta herramienta solo CONTESTA

No ejecuta el reset. Lo hace quien pregunta.

Y no es un detalle de estilo: una herramienta que solo responde **no puede destruir nada por
accidente**. El acto destructivo se queda en el bucle que llama, a la vista, en una línea que se
lee. Una herramienta que respondiera *y* borrara tendría que acertar siempre; ésta solo tiene que
no mentir.

## La trampa que tiene prohibida

Contestar 0 cuando no ha podido mirar. Si el repositorio no existe, si `git` no está, o si la
respuesta es ilegible, el veredicto es **2**, nunca 0. Un «sí, puedes borrar» por no haber podido
comprobar es la peor respuesta posible de este programa.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def head_de(repo: Path) -> str | None:
    """El HEAD actual, o None si no se pudo preguntar. NUNCA una cadena vacía por descuido."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo), capture_output=True, text=True,
            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    sha = r.stdout.strip()
    return sha or None


def quien_hay_en_medio(repo: Path, mio: str, ahora: str) -> list[str]:
    """Los commits que hay entre el tuyo y HEAD. Vacío si no se pudo saber: es informativo."""
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", f"{mio}..{ahora}"],
            cwd=str(repo), capture_output=True, text=True,
            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mio", help="el sha que hizo el agente, guardado justo despues de commitear")
    p.add_argument("--repo", default=".", help="raiz del repositorio (por defecto, el actual)")
    a = p.parse_args(argv)

    repo = Path(a.repo)
    if not repo.exists():
        print(f"NO SE PUDO SABER: no existe '{a.repo}'. No deshagas nada.")
        return 2
    if not a.mio.strip():
        print("NO SE PUDO SABER: no me has dado tu sha. No deshagas nada.")
        return 2

    ahora = head_de(repo)
    if ahora is None:
        print("NO SE PUDO SABER: git no contesta en ese directorio. No deshagas nada.")
        return 2

    if ahora == a.mio.strip():
        print(f"SIGUE SIENDO TUYO: HEAD={ahora[:12]}. Deshacer es seguro.")
        return 0

    enmedio = quien_hay_en_medio(repo, a.mio.strip(), ahora)
    print("NO ES TUYO: la rama se movio mientras trabajabas. NO deshagas.")
    print(f"  esperabas HEAD={a.mio.strip()[:12]} y encuentro HEAD={ahora[:12]}")
    if enmedio:
        print(f"  hay {len(enmedio)} commit(s) de otro en medio:")
        for l in enmedio[:5]:
            print(f"    {l}")
        if len(enmedio) > 5:
            print(f"    ... y {len(enmedio) - 5} mas")
    else:
        # Ni siquiera se pudo enumerar: se dice, porque un «no es tuyo» sin detalle
        # y un «no es tuyo con 12 commits dentro» piden cosas distintas a quien lee.
        print("  no se pudo enumerar que hay en medio (¿historias sin relacion?)")
    print("  Deja el commit del agente y revisalo a mano: perder trabajo ajeno no se ve.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
