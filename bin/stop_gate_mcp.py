"""
stop_gate_mcp.py — Stop hook para mcp_smart_context.
Ejecuta el oracle tabular y bloquea si hay regresion MRR.
Anti-loop guard + hard cap de iteraciones.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ITER_FILE = Path(tempfile.gettempdir()) / "claude_stop_gate_mcp_iter"
MAX_ITER = 3
#: La raiz del proyecto que este gate vigila. Se declara FUERA del codigo (variable de entorno)
#: porque el gate es la pieza, no el proyecto: un valor cableado aqui convierte la herramienta en
#: propiedad de una sola maquina. Si no esta puesta, se asume el repo desde el que corre.
PROJECT_DIR = os.environ.get("AGENT_GATES_PROJECT_DIR") or str(Path(__file__).resolve().parent.parent)
PYTHON_EXE = os.path.join(PROJECT_DIR, "venv", "Scripts", "python.exe")
EVAL_SCRIPT = os.path.join(PROJECT_DIR, "eval", "run_tabular_eval.py")


def _block(reason: str, context: str = "") -> None:
    print(json.dumps({
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context or reason,
        },
    }, ensure_ascii=True))
    sys.exit(0)


# ── GATE NARRATIVO · asíncrono y SELLADO (2026-08-20) ─────────────────────────────────
#
# Prometido el 2026-06-28 («cablearlo en vez de correrlo a mano») y sin hacer 54 días porque el
# obstáculo era real: el eval tarda 183 s medidos hoy (el comentario de .ralph.conf decía 60 y
# llevaba dos meses desactualizado), y CI no puede correrlo porque necesita el índice vivo, que
# no está versionado.
#
# Así que no se espera: se DISPARA suelto y se lee la próxima vez. Lo que hace que eso no sea
# una caché mentirosa es el SELLO — el resultado guarda un hash del CONTENIDO de los ficheros de
# retrieval, así que un resultado de otro árbol no se puede confundir con uno de este.
sys.path.insert(0, os.path.join(PROJECT_DIR, "eval"))

#: Ficheros cuyo cambio puede mover el MRR narrativo (HybridSearchEngine / EmbeddingManager /
#: reranker / _is_tabular_corpus viven todos ahí).
RETRIEVAL = ("src/mcp_smart_context.py",)

#: No relanzar mientras uno está corriendo. 600 s > los 183 que tarda, con margen.
_CERROJO = Path(tempfile.gettempdir()) / "claude_narrative_gate_lock"
_VIDA_CERROJO_S = 600


def gates_para_cambios(ficheros):
    """Qué gates exige haber tocado `ficheros`. Función PURA: sin disco, sin red, sin git.

    Existe como función —y no como un comentario o un mensaje— porque su ACEPTACIÓN la LLAMA.
    Comprobar que una cadena aparece en un fichero lo cumple cualquier texto suelto, y eso no
    es un gate: es la trampa que este proyecto lleva todo el día desmontando.
    """
    norm = [str(f).replace(chr(92), "/") for f in ficheros]
    return ["narrativo"] if any(r in f for f in norm for r in RETRIEVAL) else []


def _ficheros_tocados():
    """Lo cambiado respecto al último commit, incluido lo NO commiteado (que también mueve el MRR)."""
    try:
        r = subprocess.run(["git", "-C", PROJECT_DIR, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=15)
        return [l[3:].strip() for l in r.stdout.splitlines() if l[3:].strip()]
    except Exception:
        return []


def _lanzar_suelto():
    if _CERROJO.exists():
        try:
            if (time.time() - _CERROJO.stat().st_mtime) < _VIDA_CERROJO_S:
                return False  # ya hay uno corriendo
        except Exception:
            pass
    try:
        _CERROJO.write_text(str(time.time()))
        creation = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([PYTHON_EXE, os.path.join(PROJECT_DIR, "eval", "narrative_gate_bg.py")],
                         cwd=PROJECT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=creation)
        return True
    except Exception:
        return False


def _revisa_gate_narrativo():
    """`None` si no hay nada que decir; `(motivo, detalle)` si hay que bloquear."""
    if not gates_para_cambios(_ficheros_tocados()):
        return None
    try:
        from narrative_sello import leer_valido
    except Exception:
        return None  # fail-open: sin el módulo no se bloquea a nadie
    res = leer_valido(Path(PROJECT_DIR))
    if res is None:
        lanzado = _lanzar_suelto()
        print("gate narrativo: tocaste el path de retrieval y no hay medida de ESTE árbol; "
              + ("lanzado en segundo plano (~183 s), se aplica al siguiente cierre."
                 if lanzado else "ya hay uno corriendo."))
        return None
    if not res.get("ok"):
        return ("REGRESION NARRATIVA — MRR@5 por debajo del suelo tras tocar el path de "
                "retrieval. Medido sobre ESTE arbol exacto.", str(res.get("detalle"))[-800:])
    print(f"gate narrativo: OK sobre este arbol (MRR={res.get('mrr')}).")
    return None


def main() -> None:
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    # Anti-loop: si ya estamos en un stop hook activo, salir
    if payload.get("stop_hook_active"):
        sys.exit(0)

    # Bajo Ralph (loop autónomo) el gate runtime-side del loop (re-corre el oracle y
    # revierte) ya es la autoridad: evitamos oracle x2-3 por iteración y que el agente
    # "thrashee" dentro de una iteración. Ver scripts/ralph.sh (export RALPH_ACTIVE=1).
    if os.getenv("RALPH_ACTIVE") == "1":
        sys.exit(0)

    # Hard cap: max MAX_ITER iteraciones por sesion
    try:
        count = int(ITER_FILE.read_text().strip()) if ITER_FILE.exists() else 0
    except Exception:
        count = 0

    if count >= MAX_ITER:
        print(f"stop_gate_mcp: max iteraciones ({MAX_ITER}) alcanzadas — saliendo sin bloquear")
        try:
            ITER_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        sys.exit(0)

    try:
        ITER_FILE.write_text(str(count + 1))
    except Exception:
        pass

    veredicto = _revisa_gate_narrativo()
    if veredicto:
        _block(*veredicto)

    try:
        result = subprocess.run(
            [PYTHON_EXE, EVAL_SCRIPT],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=50,
        )
        output = (result.stdout or "") + (result.stderr or "")
        print(output, end="")
        if result.returncode != 0:
            _block(
                "REGRESION DETECTADA — oracle MRR@5 fallo. No puedo terminar hasta resolver.",
                output[-1000:],
            )
        # Pasó el gate: limpiar el contador para no autodesactivar el gate tras MAX_ITER (S2)
        try:
            ITER_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        sys.exit(0)
    except subprocess.TimeoutExpired:
        print("advertencia: oracle timeout (>50s) — terminando sin bloquear")
        sys.exit(0)
    except Exception as e:
        print(f"advertencia: stop_gate_mcp no disponible ({e})")
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"stop_gate_mcp: error inesperado ({e})")
        sys.exit(0)
