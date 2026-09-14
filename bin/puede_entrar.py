#!/usr/bin/env python3
"""¿Puede el agente entrar por la puerta? — la pregunta más obvia, y hasta hoy nadie la hacía.

    <py> bin/puede_entrar.py [--salida <json>] [--binario <ruta>]

    exit 0 → SÍ puede entrar.
    exit 1 → NO puede entrar. **La noche no se gasta.**
    exit 2 → no se pudo preguntar (sin binario, sin respuesta, respuesta ilegible).

## Por qué existe, y tiene fecha

MEDIDO la madrugada del 2026-09-13: la casa llevaba **tres noches desautenticada** y ningún rojo lo decía. Las
nocturnas del 11 y del 12 gastaron **10 de 10 iteraciones en 34 y 33 segundos**; la tanda del robot del 12 a las
23:00, su única iteración **con 17 tareas en la cola**. Las tres cerraron con «salió con 0» y el Programador
anotó `0x0`.

El fichero de credenciales tenía el `refreshToken` **vacío** mientras `refreshTokenExpiresAt` decía 2026-09-19:
una etiqueta que describe un token que no está. Y como el token de refresco no estaba, **no había recuperación
automática posible** — hacía falta una persona (`claude auth login`). Así que lo robusto no era arreglar el
refresco: era que la casa se entere el mismo día y que la noche no se gaste.

## La regla que no se puede duplicar, y por eso vive aquí

🔴 **Se lee el CAMPO `loggedIn`, nunca el código de salida.** MEDIDO el mismo día: `claude auth status` sale con
**0** mientras imprime `"loggedIn": false`. Un guion que mirara `$?` concluiría que todo va bien — es
`gotcha-el-exit-0-que-es-un-valor-por-defecto`. Esa regla está escrita **una vez**, aquí, y la llaman los dos
bucles; si estuviera copiada en los dos `.sh` acabaríamos con dos versiones, que es lo que `UN-SOLO-RALPH-SH`
pelea.

## La asimetría, que es deliberada y va al revés que la del gate

`el_gate_se_cayo_solo.py` ante la duda **revierte**, porque absolver de más deja el árbol roto. Aquí ante la duda
**se sigue**, porque parar de más cuesta una noche entera de trabajo por un binario que tardó en contestar. El
lado seguro no es el mismo en los dos sitios, y decirlo en voz alta evita copiar la regla de uno al otro.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

#: El campo de la respuesta. Se parsea ESTO, nunca `$?`.
CAMPO = "loggedIn"
#: Un `auth status` que tarde más que esto es «no se pudo preguntar», no «no».
TOPE_S = 25


def como_esta_la_entrada(salida=None, binario=None, tope_s: int = TOPE_S):
    """(puede, detalle). `puede` es **None** cuando no se pudo preguntar — y eso NO es «no».

    Distinguir «me ha dicho que no» de «no he podido preguntar» es todo el asunto: si un corte de red o un
    binario ausente se leyeran como «desautenticado», el aviso saltaría por motivos que no son el suyo, y un
    aviso que salta por cualquier cosa se aprende a ignorar en dos semanas.
    """
    crudo = salida
    if crudo is None:
        exe = binario or shutil.which("claude")
        if not exe:
            return None, "`claude` no está en el PATH de esta máquina"
        try:
            r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=tope_s)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, "`claude auth status` no contestó (" + type(e).__name__ + ")"
        crudo = r.stdout or ""
    try:
        d = json.loads(crudo)
    except Exception:
        return None, "`claude auth status` no devolvió un JSON legible"
    if not isinstance(d, dict) or CAMPO not in d:
        return None, "la respuesta no trae el campo `" + CAMPO + "`"
    # `authMethod` se usa en el mensaje. El `email` que también viene NO se toca: esto acaba en logs.
    return d[CAMPO] is True, str(d.get("authMethod") or "?")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="puede el agente entrar por la puerta?")
    p.add_argument("--salida", default=None, help="respuesta de `claude auth status`, para probar sin la CLI")
    p.add_argument("--binario", default=None)
    p.add_argument("--tope-segundos", type=int, default=TOPE_S)
    a = p.parse_args(argv)

    puede, detalle = como_esta_la_entrada(a.salida, a.binario, a.tope_segundos)
    if puede is None:
        print("no se pudo preguntar si el agente puede entrar: " + str(detalle), file=sys.stderr)
        return 2
    if not puede:
        print("EL AGENTE NO PUEDE ENTRAR: `claude auth status` dice `" + CAMPO + ": false`. Toda tanda de esta"
              " noche gastaría sus iteraciones sin hacer nada.", file=sys.stderr)
        print("   Lo arregla una persona:  claude auth login", file=sys.stderr)
        print("   (sin token de refresco no hay recuperación automática posible)", file=sys.stderr)
        return 1
    print("el agente puede entrar (" + str(detalle) + ")", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
