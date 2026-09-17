#!/usr/bin/env python3
"""¿Hay trabajo que sólo existe FUERA de la rama principal? — la pregunta antes de limpiar.

    <py> bin/nada_vive_solo_fuera_de_main.py [--repo RUTA] [--rama main] [--acepta RUTA ...]

    exit 0 → NO: todo lo que hay fuera está también en la rama principal. **Limpiar es seguro.**
    exit 1 → SÍ: hay ficheros que sólo existen fuera. **Míralos antes de borrar nada.**
    exit 2 → NO SE PUDO SABER: no hay repo, o git no contesta. **No limpies.**

## Por qué existe, y tiene fecha

Un agente que trabaja solo acumula sitios donde el trabajo se esconde: ramas de prueba que se
borran, commits que quedan vivos sólo por el reflog, `stash` olvidados, worktrees abandonados. Y
la costumbre sana —limpiar lo que sobra— es la que destruye lo que estaba escondido.

**El caso real (2026-09-16).** Había un `stash` de 24 días. Su contenido propio eran dos líneas
de comentario sin valor, sobre una versión de un fichero que ya no existía. Lo sensato parecía
borrarlo.

🔑 **Pero era lo único que mantenía alcanzable el commit padre**, de una rama ya borrada. Y en ese
commit vivían dos ficheros que la rama principal no tenía: los datos de prueba de un defecto que
la auditoría del proyecto marcaba en rojo. Borrar el stash los habría destruido sin dejar rastro.
**Lo que parecía basura era el ancla.**

## Por qué NO pregunta «¿hay stashes?», que es la pregunta obvia

Un `stash` no es un problema por existir, y el de ese día tenía contenido intrascendente. Un
comprobador que diga *«hay 1 stash»* sale rojo cada noche **para siempre**, hasta que alguien lo
borre — y un aviso que no se apaga enseña a ignorar los avisos. Peor: empuja justo al gesto que
destruye.

Lo que importa no es el escondite: es el **contenido**. Un fichero que sólo existe fuera de la
rama principal es **raro por construcción**, así que cuando esto habla merece leerse.

## Se compara el CONTENIDO, no la RUTA

Un rescate normalmente renombra el fichero y le añade una cabecera explicando de dónde salió. Si
la comparación fuera por ruta, ese rescate se quedaría **rojo para siempre** y el comprobador se
volvería ruido. Así que se busca en la rama principal la **línea más distintiva** —la más larga—
del fichero. Sobrevive al renombrado y a los comentarios añadidos.

## Los cuatro escondites, y el cuarto no es un objeto de git

1. ramas sin fusionar
2. commits huérfanos, vivos sólo por el reflog
3. lo que cuelga de un `stash`
4. lo **sin commitear en otro worktree** del mismo repositorio — que `git rev-list` no ve, porque
   nunca llegó a ser un objeto

## La trampa que tiene prohibida, y es la que más cuesta ver

**Contestar 0 cuando no ha podido mirar.** Un fichero cuyo contenido no tiene ninguna línea lo
bastante distintiva para buscarla **no está verificado**, y decir que está a salvo sería peor que
callarse. Eso sale aparte, como *no se pudo comprobar*, y cuenta como 1, nunca como 0.

*(La primera versión de esta comprobación hacía exactamente eso: un `continue` silencioso que
daba por salvado cualquier fichero de líneas cortas. Lo cazó su propia mutación.)*

## Por qué sólo CONTESTA

No borra, no rescata, no commitea. Lo hace quien pregunta. Una herramienta que sólo responde no
puede destruir nada por accidente, y el acto queda a la vista de quien lo escribe.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

#: Una línea con menos caracteres que esto no sirve para buscar: casa con cualquier cosa. El
#: umbral es deliberadamente bajo — el coste de un falso «no se pudo comprobar» es una mirada, y
#: el de un falso «está a salvo» es trabajo perdido sin rastro.
MINIMO_DISTINTIVO = 12


def _git(repo: Path, *args: str, cwd: Path | None = None) -> str | None:
    """La salida, o None si no se pudo preguntar. NUNCA una cadena vacía por descuido."""
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd or repo), *args],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def fuera_de(repo: Path, rama: str, acepta: set[str],
             casas: tuple[str, ...] = ()) -> tuple[list[str], list[str]] | None:
    """(ficheros que sólo existen fuera, ficheros que no se pudieron comprobar), o None si no
    se pudo ni empezar."""
    # `--not` acepta varias referencias: un fichero que vive en CUALQUIERA de ellas ya tiene casa.
    #
    # Por que hace falta mas de una rama, y lo enseño un repo real: `main` no siempre es el
    # destino del trabajo. En un repositorio PUBLICO, `main` es el escaparate — lo que ve quien
    # abre el proyecto — y la maquinaria interna se queda fuera A PROPOSITO. Ahi los ficheros «solo
    # fuera de main» eran siete, y estaban todos en una rama llamada
    # `respaldo/antes-del-aplastado-<fecha>`: no era trabajo perdido, era alguien haciendo
    # exactamente lo correcto, y esta comprobacion lo señalaba como problema.
    #
    # 🔑 Se declaran RAMAS y no patrones de fichero, y la diferencia importa: una rama con ese
    # nombre es un acto deliberado de una persona, no una adivinanza mia. Y degrada del lado
    # seguro — el dia que alguien borre la rama, sus ficheros vuelven a salir en la alarma.
    commits = _git(repo, "rev-list", "--all", "--reflog", "--not", rama, *casas)
    if commits is None:
        return None

    solo_fuera: list[str] = []
    sin_comprobar: list[str] = []
    vistos: set[str] = set()

    for c in [x for x in commits.split() if x]:
        tocados = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", c)
        if tocados is None:
            continue
        for rel in [x.strip() for x in tocados.splitlines() if x.strip()]:
            if rel in vistos or rel in acepta or (repo / rel).exists():
                continue
            vistos.add(rel)
            # Sólo los BLOBS son contenido. Un `commit` ahí es un gitlink —un submódulo o una
            # carpeta de worktree que alguien commiteó— y no hay nada que salvar dentro: su
            # contenido vive en otro sitio.
            #
            # ⚠️ Medido: sin este filtro, un repositorio real daba **16** ficheros «sólo fuera» y
            # **15 eran gitlinks** de worktrees de agente. Un aviso con 15 de 16 de ruido no se
            # lee, así que el único hallazgo verdadero se habría perdido dentro de su propia
            # alarma. Y se filtra por TIPO y no por nombre de ruta a propósito: excluir por
            # patrón esconde lo que no se te ocurrió nombrar.
            if (_git(repo, "cat-file", "-t", f"{c}:{rel}") or "").strip() != "blob":
                continue
            cuerpo = _git(repo, "show", f"{c}:{rel}")
            if not cuerpo or not cuerpo.strip():
                continue                      # vacío o ilegible: no hay contenido que salvar
            lineas = [l.strip() for l in cuerpo.splitlines()
                      if len(l.strip()) > MINIMO_DISTINTIVO]
            if not lineas:
                sin_comprobar.append(rel)     # NO es «está a salvo»
                continue
            # Se prueban las CINCO lineas mas distintivas, no solo la mas larga.
            #
            # ⚠️ Medido en un repo real: un fichero que se PARTIO en tres al refactorizar salia
            # como «solo fuera», y su contenido estaba entero en la rama, repartido. Fallaba
            # porque su linea mas larga era la firma de una funcion que el refactor habia
            # REFORMATEADO: un renombrado sobrevive a buscar una linea literal, un refactor no.
            # Con cinco intentos, una linea reformateada ya no condena al fichero entero.
            #
            # 🔑 Y sigue siendo comparacion LITERAL: no se parecen lineas, se buscan. Si ninguna
            # de las cinco esta, el contenido de verdad no esta.
            if any(_git(repo, "grep", "-l", "-F", "--", d, r)
                   for d in sorted(lineas, key=len, reverse=True)[:5]
                   for r in (rama, *casas)):
                continue                      # alguna linea distintiva esta en casa: a salvo
            solo_fuera.append(rel)
    return solo_fuera, sin_comprobar


def worktrees_sucios(repo: Path) -> list[tuple[str, int]]:
    """Los OTROS worktrees con cambios sin commitear. Vacío si no se pudo saber: informativo."""
    lista = _git(repo, "worktree", "list", "--porcelain")
    if not lista:
        return []
    fuera: list[tuple[str, int]] = []
    for linea in lista.splitlines():
        if not linea.startswith("worktree "):
            continue
        wt = Path(linea[len("worktree "):].strip())
        try:
            if wt.resolve() == repo.resolve():
                continue
        except OSError:
            continue
        s = _git(repo, "status", "--porcelain", cwd=wt)
        if s:
            n = len([x for x in s.splitlines() if x.strip()])
            if n:
                fuera.append((wt.name, n))
    return fuera


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".", help="raiz del repositorio (por defecto, el actual)")
    p.add_argument("--rama", default="main", help="la rama principal (por defecto, main)")
    p.add_argument("--acepta", nargs="*", default=[],
                   help="rutas cuya perdida se acepta POR ESCRITO; el motivo va donde se llama")
    p.add_argument("--tambien-en", nargs="*", default=[], metavar="RAMA",
                   help="otras ramas que cuentan como casa legitima: un respaldo declarado, la "
                        "rama de un robot. Si se borra una, sus ficheros vuelven a salir")
    a = p.parse_args(argv)

    repo = Path(a.repo)
    if not (repo / ".git").exists():
        print(f"NO SE PUDO SABER: '{a.repo}' no parece un repositorio. No limpies nada.")
        return 2
    if _git(repo, "rev-parse", "--verify", a.rama) is None:
        print(f"NO SE PUDO SABER: la rama '{a.rama}' no existe aqui. No limpies nada.")
        return 2

    casas = tuple(a.tambien_en)
    for c in casas:
        if _git(repo, "rev-parse", "--verify", c) is None:
            print(f"NO SE PUDO SABER: la casa declarada '{c}' no existe. No limpies nada.")
            return 2
    r = fuera_de(repo, a.rama, set(a.acepta), casas)
    if r is None:
        print("NO SE PUDO SABER: git no contesta en ese directorio. No limpies nada.")
        return 2
    solo_fuera, sin_comprobar = r
    sucios = worktrees_sucios(repo)

    if not (solo_fuera or sin_comprobar or sucios):
        extra = (" (ni de " + ", ".join(casas) + ")") if casas else ""
        print(f"NADA VIVE SOLO FUERA DE {a.rama}{extra}: ni en stash, ni en rama suelta, ni en worktree.")
        return 0

    if solo_fuera:
        print(f"SOLO EXISTEN FUERA DE {a.rama} ({len(solo_fuera)}):")
        for x in solo_fuera[:10]:
            print(f"    {x}")
        if len(solo_fuera) > 10:
            print(f"    ... y {len(solo_fuera) - 10} mas")
    if sin_comprobar:
        print(f"NO SE PUDO COMPROBAR ({len(sin_comprobar)}) — sin ninguna linea distintiva que "
              "buscar. NO es «esta a salvo»:")
        for x in sin_comprobar[:5]:
            print(f"    {x}")
    if sucios:
        print("WORKTREES CON CAMBIOS SIN COMMITEAR:")
        for nombre, n in sucios[:5]:
            print(f"    {nombre}: {n} fichero(s)")
    print("  Miralo antes de borrar el stash o la rama: lo que parece basura puede ser el ancla.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
