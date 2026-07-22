"""
CLI de hipercampo — para usarlo desde el terminal y, sobre todo, desde HOOKS
(modo "sináptico": la memoria se dispara sola en cada turno de la conversación).

    hipercampo serve                 # arranca el servidor MCP (stdio)
    hipercampo assist "texto"        # ¿qué toca hacer en este momento? (para hooks)
    hipercampo recall "consulta"     # recuperar
    hipercampo remember "texto"      # guardar (respeta el veto por sorpresa)
    hipercampo muse "tema"           # inspiración: conexiones indirectas y latentes
    hipercampo sleep                 # consolidar + olvidar + soñar
    hipercampo stats                 # estado de la memoria
    hipercampo backup [destino]      # copia de seguridad consistente
    hipercampo servers               # qué servidores MCP hay vivos y desde cuándo
    hipercampo restart               # reiniciarlos tras actualizar (el cliente los relanza)
    hipercampo doctor                # diagnóstico: ruta, permisos, versión, deps
    hipercampo version

Variables: HIPERCAMPO_DB, HIPERCAMPO_NAMESPACE, HIPERCAMPO_SEMANTIC,
HIPERCAMPO_AUTOSLEEP_EVERY, HIPERCAMPO_MAX_MEMORIES, HIPERCAMPO_REDACT_SECRETS.
"""

import argparse
import json
import os
import re
import sys
import time

try:                                                  # salida UTF-8 en Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _hc():
    from .config import db_path
    from .memory import Hipercampo
    return Hipercampo(db_path(), namespace=os.environ.get("HIPERCAMPO_NAMESPACE", "default"))


def _print(obj, plain=False):
    if plain and isinstance(obj, list):
        for h in obj:
            print(f"- {h.get('text', '')}")
    elif plain and isinstance(obj, dict) and "result" in obj:
        print(f"[{obj.get('action')}] {obj.get('why')}")
        for h in obj.get("result") or []:
            print(f"- {h.get('text', '')}")
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_hook(_args) -> int:
    """Modo SINÁPTICO: pensado para el hook UserPromptSubmit de Claude Code.

    Lee el JSON del hook por stdin, decide qué toca (assist) y devuelve el contexto
    a inyectar en el turno. Si no hay nada relevante, no inyecta nada (se calla)."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    prompt = ""
    for clave in ("prompt", "user_prompt", "userPrompt", "message", "input"):
        v = payload.get(clave)
        if isinstance(v, str) and v.strip():
            prompt = v.strip()
            break
    # El IDE puede colar bloques propios (<ide_opened_file>, <system-reminder>…):
    # no son texto del usuario, así que no deben decidir qué recuerda hipercampo.
    prompt = re.sub(r"<[a-zA-Z_-]+>.*?</[a-zA-Z_-]+>", " ", prompt, flags=re.S).strip()
    if not prompt:
        print("{}")
        return 0
    try:
        hc = _hc()
        try:
            r = hc.assist(prompt)
        finally:
            hc.store.close()
    except Exception as e:
        print(json.dumps({"systemMessage": f"hipercampo no pudo responder: {e}"}))
        return 0

    accion = r.get("action")
    if accion in (None, "nothing"):
        print("{}")                      # nada relevante: no molestar
        return 0

    lineas = [f"[memoria · {accion}] {r.get('why', '')}"]
    for h in r.get("result") or []:
        lineas.append(f"- {h.get('text', '')}")
    if r.get("sugerencia"):
        lineas.append(f"(sugerencia: {r['sugerencia']})")
        if r.get("candidato"):
            lineas.append(f"(candidato #{r['candidato']['id']}: {r['candidato']['text']})")
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                               "additionalContext": "\n".join(lineas)},
        "suppressOutput": True}, ensure_ascii=False))
    return 0


def _describe(p: dict) -> str:
    cuando = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p["arranque"]))
              if p.get("arranque") else "?")
    edad = ""
    if p.get("arranque"):
        mins = (time.time() - p["arranque"]) / 60
        edad = f" ({mins/60:.1f} h)" if mins >= 90 else f" ({mins:.0f} min)"
    linea = f"  pid {p['pid']:<7} arrancado {cuando}{edad}"
    if p.get("db"):
        linea += f"\n{'':14}BD {p['db']}"
    return linea


def cmd_servers(_args) -> int:
    """Qué servidores hay vivos. Sirve para ver de un vistazo si alguno lleva
    demasiado tiempo en pie (= código viejo) o si se han acumulado huérfanos."""
    from . import __version__
    from .procs import listar
    procesos = listar()
    if not procesos:
        print("No hay ningún servidor MCP de hipercampo en marcha.")
        print("(el cliente lo arranca solo la primera vez que usa una herramienta)")
        return 0
    print(f"hipercampo {__version__} instalado · {len(procesos)} servidor(es) en marcha:")
    for p in procesos:
        print(_describe(p))
    print("\nEl proceso carga el código al arrancar: si has actualizado hipercampo "
          "después\nde esa hora, ese servidor sigue sirviendo la versión anterior. "
          "`hipercampo restart`\nlos termina y el cliente los vuelve a levantar solo.")
    return 0


def cmd_restart(args) -> int:
    """Termina los servidores para que el cliente los levante con el código actual."""
    from .procs import listar, terminar
    procesos = listar()
    if not procesos:
        print("No hay ningún servidor en marcha: no hay nada que reiniciar.")
        print("El cliente arrancará uno nuevo (ya con el código actual) al usarlo.")
        return 0
    print(f"{len(procesos)} servidor(es) en marcha:")
    for p in procesos:
        print(_describe(p))
    if args.dry_run:
        print("\n(--dry-run: no se ha tocado nada)")
        return 0

    estado = terminar([p["pid"] for p in procesos])
    print()
    for pid, que in estado.items():
        print(f"  pid {pid:<7} {que}")
    quedan = [p for p in listar() if p["pid"] in estado]
    if quedan:
        print("\nNO se pudieron cerrar: " + ", ".join(str(p["pid"]) for p in quedan))
        print("Quizá pertenecen a otro usuario; ciérralos a mano o reinicia el cliente.")
        return 1
    print("\nListo. NO hace falta arrancarlos: el cliente MCP levanta uno nuevo, con el\n"
          "código actual, la próxima vez que use una herramienta de hipercampo.")
    return 0


def cmd_doctor(_args) -> int:
    """Diagnóstico rápido: ¿está todo en su sitio para funcionar?"""
    from . import __version__
    from .config import db_path
    ruta = db_path()
    print(f"hipercampo {__version__}")
    print(f"python     {sys.version.split()[0]}")
    print(f"BD         {os.path.abspath(ruta)}")
    carpeta = os.path.dirname(os.path.abspath(ruta)) or "."
    print(f"carpeta    {'existe' if os.path.isdir(carpeta) else 'NO existe'}"
          f" · {'escribible' if os.access(carpeta, os.W_OK) else 'SIN permiso de escritura'}")
    print(f"namespace  {os.environ.get('HIPERCAMPO_NAMESPACE', 'default')}")
    for mod, etiqueta in (("numpy", "numpy"), ("mcp", "mcp (servidor)"),
                          ("sentence_transformers", "semántica (opcional)")):
        try:
            __import__(mod)
            print(f"dep        {etiqueta}: OK")
        except Exception:
            print(f"dep        {etiqueta}: no instalado")
    try:
        hc = _hc()
        salud = hc.store.health(full=getattr(_args, "full", False))
        print(f"esquema    version {hc.store.db.execute('PRAGMA user_version').fetchone()[0]}"
              f" (esperada {hc.store.SCHEMA_VERSION})")
        print(f"salud      {'SANA' if salud['sana'] else 'CON PROBLEMAS'} · "
              f"{salud['comprobacion']}={salud['integridad']} · "
              f"escribible={salud['escribible']}")
        print("memoria    ", json.dumps(hc.stats(), ensure_ascii=False, default=str))
        hc.store.close()
        return 0
    except Exception as e:
        print(f"ERROR abriendo la memoria: {e}")
        return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="hipercampo", description="Memoria viva para agentes")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="arranca el servidor MCP (stdio)")
    sub.add_parser("stats", help="estado de la memoria")
    sub.add_parser("sleep", help="consolidar + olvidar + soñar")
    dr = sub.add_parser("doctor", help="diagnóstico del entorno")
    dr.add_argument("--full", action="store_true",
                    help="integrity_check completo (más lento) en vez de quick_check")
    sub.add_parser("hook", help="modo sináptico: para el hook UserPromptSubmit")
    sub.add_parser("servers", help="qué servidores MCP hay en marcha y desde cuándo")
    rs = sub.add_parser("restart", help="reiniciar los servidores tras actualizar")
    rs.add_argument("--dry-run", action="store_true",
                    help="enseñar qué se cerraría, sin cerrar nada")
    sub.add_parser("version", help="versión instalada")
    for nombre, ayuda in (("assist", "qué toca hacer en este momento (hooks)"),
                          ("recall", "recuperar"), ("muse", "inspiración"),
                          ("remember", "guardar")):
        sp = sub.add_parser(nombre, help=ayuda)
        sp.add_argument("text", nargs="*", help="texto o consulta")
        sp.add_argument("--plain", action="store_true", help="salida legible, no JSON")
        if nombre == "remember":
            sp.add_argument("--importance", type=float, default=0.5)
            sp.add_argument("--confidence", type=float, default=0.5)
    bk = sub.add_parser("backup", help="copia de seguridad consistente")
    bk.add_argument("dest", nargs="?")
    lg = sub.add_parser("log", help="qué ha decidido hipercampo últimamente")
    lg.add_argument("-n", type=int, default=20, help="cuántas líneas")
    args = p.parse_args(argv)

    if args.cmd in (None, "version"):
        from . import __version__
        print(__version__ if args.cmd == "version" else f"hipercampo {__version__}\n")
        if args.cmd is None:
            p.print_help()
        return 0
    if args.cmd == "serve":
        from .server import main as serve
        serve(); return 0
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "hook":
        return cmd_hook(args)
    if args.cmd == "servers":
        return cmd_servers(args)
    if args.cmd == "restart":
        return cmd_restart(args)
    if args.cmd == "backup":
        from .backup import backup
        print("Copia creada en:", backup(args.dest)); return 0
    if args.cmd == "log":
        from . import audit
        from .config import db_path
        audit.set_logfile(db_path())
        lineas = audit.tail(args.n)
        print(f"# {audit.logfile() or '(registro desactivado)'}")
        print("\n".join(lineas) if lineas else "(sin actividad registrada todavía)")
        return 0

    hc = _hc()
    try:
        if args.cmd == "stats":
            _print(hc.stats())
        elif args.cmd == "sleep":
            _print(hc.sleep())
        else:
            texto = " ".join(getattr(args, "text", []) or []).strip()
            if not texto:
                print("Falta el texto.", file=sys.stderr); return 2
            if args.cmd == "assist":
                _print(hc.assist(texto), plain=args.plain)
            elif args.cmd == "recall":
                _print(hc.recall(texto), plain=args.plain)
            elif args.cmd == "muse":
                _print(hc.muse(texto), plain=args.plain)
            elif args.cmd == "remember":
                _print(hc.remember(texto, args.importance, args.confidence))
        return 0
    finally:
        hc.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
