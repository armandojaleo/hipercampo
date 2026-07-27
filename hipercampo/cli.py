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
    hipercampo log [-f] [-g texto]   # qué ha decidido y por qué (en vivo con -f)
    hipercampo identity              # qué se ha aprendido trabajando
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
from typing import Any

from . import audit, budget

try:                                                  # salida UTF-8 en Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
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
    # El JSON del hook SIEMPRE viene en UTF-8. Leer `sys.stdin` como texto usa la
    # codificación local (en Windows, cp1252) y convierte «¿añadelo?» en «Â¿aÃ±adelo?»:
    # la memoria acababa guardando y registrando el texto ya roto. Se leen bytes.
    try:
        crudo = sys.stdin.buffer.read()
    except (AttributeError, ValueError):          # stdin sustituido (tests)
        crudo = sys.stdin.read()
    if isinstance(crudo, bytes):
        crudo = crudo.decode("utf-8", "replace")
    try:
        payload = json.loads(crudo)
    except Exception:
        payload = {}
    # Al ARRANCAR una sesión no hay pregunta que responder: lo que toca es
    # recordar quién se es trabajando, para no empezar de cero.
    if payload.get("hook_event_name") == "SessionStart":
        try:
            hc = _hc()
            try:
                r = hc.identity()
            finally:
                hc.close()
        except Exception:
            print("{}")
            return 0
        if not r.get("n"):
            print("{}")
            return 0
        # La identidad se paga UNA vez por sesión, así que su presupuesto es más
        # generoso que el de cada turno; pero techo tiene, o crece sin freno según
        # se van aprendiendo reglas.
        cabecera = "[memoria · identidad de trabajo] aprendido en sesiones anteriores:"
        lineas, gasto = budget.ajustar([cabecera] + r["texto"].splitlines(),
                                       budget.IDENTITY_BUDGET)
        audit.log("tokens", f"identidad {gasto['tokens']} tok"
                  + (f" (de {gasto['original']})" if gasto.get("original") else ""))
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(lineas)},
            "suppressOutput": True}, ensure_ascii=False))
        return 0

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
            hc.close()
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

    # PRESUPUESTO. Sin techo, el coste crece con la memoria: un recuerdo
    # consolidado puede ocupar media pantalla y entrar entero en cada turno. Se
    # recorta a lo relevante, y el recorte se DICE (nunca un silencio).
    lineas, gasto = budget.ajustar(lineas)

    # Si NADA cabía, lo que queda es una cabecera y un aviso de que falta algo: 46
    # tokens (medido) para no aportar un solo dato. Peor que callarse, porque se
    # paga igual y encima el modelo no sabe qué pedir. Se calla, que es gratis.
    # Ojo: "cuerpo" no es solo recuerdos —una sugerencia de guardar también lo es—,
    # así que se descarta la cabecera y el aviso, y se mira si queda algo.
    aviso = budget._aviso(gasto.get("omitidas", 0), gasto.get("presupuesto", 0))
    if not [ln for ln in lineas[1:] if ln != aviso]:
        audit.log("tokens", "0 tok: nada cabía en el presupuesto, me callo",
                  presupuesto=gasto.get("presupuesto"), original=gasto.get("original"))
        print("{}")
        return 0

    audit.log("tokens", f"inyectados {gasto['tokens']} tok"
              + (f" (de {gasto['original']}, presupuesto {gasto['presupuesto']})"
                 if gasto.get("original") else ""))
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
    objetivo = getattr(args, "pids", None)
    if objetivo:                                       # cerrar solo los pedidos
        try:
            quiero = {int(x) for x in objetivo.split(",") if x.strip()}
        except ValueError:
            print("--pids debe ser una lista de números separados por comas.", file=sys.stderr)
            return 2
        procesos = [p for p in procesos if p["pid"] in quiero]
        if not procesos:
            print("Ninguno de esos pids es un servidor de hipercampo en marcha.")
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


def cmd_identity(_args) -> int:
    """Qué se ha aprendido trabajando (lo que sobrevive a cerrar la sesión)."""
    hc = _hc()
    try:
        r = hc.identity()
        if not r.get("n"):
            print("Todavía no hay identidad de trabajo aprendida.")
            print("Se construye con `hc_learn` cuando algo enseña cómo trabajar mejor.")
            return 0
        print(f"# identidad de trabajo · {r['n']} cosa(s) aprendidas\n")
        print(r["texto"])
        return 0
    finally:
        hc.close()


def cmd_list(args) -> int:
    """Vuelca las memorias: JSON para el visor de VS Code, o una tabla legible."""
    import time as _t

    from .config import db_path
    from .store import Store
    ns = args.namespace or os.environ.get("HIPERCAMPO_NAMESPACE", "default")
    s = Store(db_path(), namespace=ns)
    try:
        filas = s.dump(all_namespaces=args.all_namespaces,
                       include_dormant=args.include_dormant,
                       kind=args.kind, limit=args.limit, order=args.sort)
    finally:
        s.close()

    if args.json:
        print(json.dumps({"namespace": ns, "all_namespaces": args.all_namespaces,
                          "db": os.path.abspath(db_path()),
                          "count": len(filas), "memories": filas},
                         ensure_ascii=False, default=str))
        return 0

    if not filas:
        print("No hay memorias que mostrar en este criterio.")
        return 0
    ahora = _t.time()
    print(f"{len(filas)} memoria(s)"
          + (" · todo el fichero" if args.all_namespaces else f" · contexto «{ns}»") + "\n")
    for m in filas:
        edad_d = (ahora - m["last_access"]) / 86400
        marcas = "".join(c for c, on in (("💤", m["dormant"]), ("📦", m["consolidated"]),
                                         ("↩", m["superseded"])) if on)
        cab = f"#{m['id']} [{m['kind']}]"
        if args.all_namespaces:
            cab += f" ⟨{m['namespace']}⟩"
        texto = m["text"].replace("\n", " ")
        if len(texto) > 100:
            texto = texto[:97] + "…"
        print(f"{cab} {marcas}")
        print(f"   {texto}")
        print(f"   imp {m['importance']:.2f} · fiab {m['confidence']:.2f} · "
              f"fuerza {m['strength']:.2f} · usos {m['access_count']} · "
              f"visto hace {edad_d:.0f}d")
    return 0


def cmd_graph(args) -> int:
    """Vuelca el grafo asociativo (nodos + aristas) en JSON para el mapa del visor."""
    from .config import db_path, paused
    from .store import Store
    ns = args.namespace or os.environ.get("HIPERCAMPO_NAMESPACE", "default")
    s = Store(db_path(), namespace=ns)
    try:
        nodos = s.dump(all_namespaces=args.all_namespaces, include_dormant=True)
        aristas = s.links_dump(all_namespaces=args.all_namespaces)
    finally:
        s.close()
    # Solo aristas cuyos DOS extremos están entre los nodos mostrados (no colgar).
    ids = {n["id"] for n in nodos}
    aristas = [e for e in aristas if e["src"] in ids and e["dst"] in ids]
    print(json.dumps({"namespace": ns, "all_namespaces": args.all_namespaces,
                      "db": os.path.abspath(db_path()), "paused": paused(),
                      "nodes": nodos, "edges": aristas}, ensure_ascii=False, default=str))
    return 0


def cmd_dream(args) -> int:
    """Propone PUENTES entre recuerdos que comparten un asociado común pero no están
    conectados: ideas —hipótesis— que la memoria sugiere. En DRY-RUN: solo las muestra,
    no las persiste ni contamina la evidencia (esa es la regla del sueño)."""
    hc = _hc()
    try:
        d = hc.dream(max_bridges=max(1, int(getattr(args, "max", 8))), dry_run=True)
    finally:
        hc.close()
    if getattr(args, "json", False):
        print(json.dumps(d, ensure_ascii=False, default=str))
    else:
        for b in d.get("bridges", []):
            print(f"· {b['hypothesis']}")
        if not d.get("bridges"):
            print("Sin ideas nuevas por ahora (nada que conectar).")
    return 0


def cmd_dormant(args) -> int:
    """Adormece (o despierta con --wake) recuerdos por id. Escritura: solo el propio
    contexto. Es el «olvidar» reversible del visor, distinto de purgar (físico)."""
    from .config import db_path
    from .store import Store
    ns = args.namespace or os.environ.get("HIPERCAMPO_NAMESPACE", "default")
    try:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
    except ValueError:
        print("--ids debe ser una lista de números separados por comas.", file=sys.stderr)
        return 2
    s = Store(db_path(), namespace=ns)
    try:
        s.set_dormant(ids, dormant=not args.wake)
    finally:
        s.close()
    accion = "despiertos" if args.wake else "adormecidos"
    print(json.dumps({accion: ids, "namespace": ns}, ensure_ascii=False))
    return 0


def cmd_budget(args) -> int:
    """Ver o fijar el presupuesto de tokens del hook (lo que la memoria inyecta por
    turno). Se persiste junto al .db y el hook lo respeta al turno siguiente, sin
    reiniciar nada. La variable HIPERCAMPO_HOOK_BUDGET, si está, manda por encima."""
    from . import config
    if getattr(args, "reset", False):
        config.set_hook_budget(None)
    elif args.set is not None:
        config.set_hook_budget(max(0, int(args.set)))
    env = (os.environ.get("HIPERCAMPO_HOOK_BUDGET") or "").strip()
    persistido = config.hook_budget_persisted()
    if env.isdigit():
        efectivo, fuente = int(env), "entorno"
    elif persistido is not None:
        efectivo, fuente = persistido, "guardado"
    else:
        efectivo, fuente = 350, "por defecto"
    print(json.dumps({"hook_budget": efectivo, "fuente": fuente,
                      "guardado": persistido, "por_defecto": 350}, ensure_ascii=False))
    return 0


def cmd_reclassify(args) -> int:
    """Mueve recuerdos PROPIOS a otro contexto (curación del dueño). Escritura: solo
    el contexto origen; no toca lo enlazado ni lo ajeno. Recoloca los enlaces."""
    from .config import db_path
    from .store import Store
    ns = args.namespace or os.environ.get("HIPERCAMPO_NAMESPACE", "default")
    destino = (args.to or "").strip()
    if not destino:
        print("Falta --to (contexto destino).", file=sys.stderr); return 2
    try:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
    except ValueError:
        print("--ids debe ser una lista de números separados por comas.", file=sys.stderr)
        return 2
    s = Store(db_path(), namespace=ns)
    try:
        movidos = s.reclassify(ids, destino)
    finally:
        s.close()
    print(json.dumps({"movidos": movidos, "de": ns, "a": destino}, ensure_ascii=False))
    return 0


def cmd_purge(args) -> int:
    """Borrado FÍSICO y seguro. Irreversible: se enseña primero qué se va a borrar
    (ensayo) y se pide confirmación, salvo --yes. Es lo contrario del olvido normal,
    que solo adormece; esto quita el texto del fichero y recupera el espacio."""
    if (args.ids is None) == (args.older_than is None):   # 0 días es válido, no "falta"
        print("Elige UNO: --ids 3,7,9  o  --older-than DÍAS.", file=sys.stderr)
        return 2
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    if getattr(args, "namespace", None):
        os.environ["HIPERCAMPO_NAMESPACE"] = args.namespace   # acotar a ese contexto
    hc = _hc()
    try:
        ensayo = hc.purge(older_than_days=args.older_than, ids=ids, dry_run=True)
        if "error" in ensayo:
            print(ensayo["error"], file=sys.stderr); return 2
        objetivo = ensayo["ids"]
        if not objetivo:
            print("Nada coincide con ese criterio: no hay nada que purgar.")
            return 0
        print(f"Se BORRARÁN FÍSICAMENTE {len(objetivo)} recuerdo(s): "
              f"{', '.join(map(str, objetivo))}")
        print("Esto es irreversible (no es el olvido, que solo adormece).")
        if not args.yes:
            try:
                if input("¿Seguro? escribe 'si' para continuar: ").strip().lower() not in (
                        "si", "sí", "s", "yes", "y"):
                    print("Cancelado."); return 0
            except EOFError:
                print("\nSin confirmación (usa --yes para no interactivo). Cancelado.")
                return 1
        r = hc.purge(older_than_days=args.older_than, ids=ids, vacuum=not args.no_vacuum)
        _print(r)
        return 0
    finally:
        hc.close()


def cmd_log(args) -> int:
    """Qué ha decidido hipercampo: el registro, con filtros y en vivo."""
    import time as _t

    from . import audit
    from .config import db_path
    audit.set_logfile(db_path())
    ruta = audit.logfile()
    if getattr(args, "ruta", False):
        print(ruta or "(registro desactivado: HIPERCAMPO_LOG=0)")
        return 0
    if not ruta:
        # Log desactivado (HIPERCAMPO_LOG=0). Para el visor NO es un error: es un
        # registro vacío, y así la pestaña Registro lo enseña con elegancia en vez
        # de romperse. Para el humano, un aviso claro.
        if getattr(args, "json", False):
            print(json.dumps({"path": None, "enabled": False, "entries": []},
                             ensure_ascii=False))
            return 0
        print("El registro está desactivado (HIPERCAMPO_LOG=0).")
        return 1

    accion = "ERROR" if args.errores else args.accion

    def leer(n):
        return audit.tail(n, contiene=args.grep, solo_hoy=args.hoy, accion=accion)

    if getattr(args, "json", False):        # salida estructurada para el visor
        entradas = [_entrada_log(ln) for ln in leer(args.n if args.n else 200)]
        print(json.dumps({"path": ruta, "entries": entradas},
                         ensure_ascii=False, default=str))
        return 0

    filtros = " · ".join(f for f in (
        f"acción={accion}" if accion else "",
        f"contiene «{args.grep}»" if args.grep else "",
        "solo hoy" if args.hoy else "") if f)
    print(f"# {ruta}{' · ' + filtros if filtros else ''}")

    lineas = leer(args.n)
    if not lineas:
        print("(nada coincide con el filtro)" if filtros else "(sin actividad todavía)")
        if not args.follow:
            print("\nAcciones vistas en el registro: "
                  + (", ".join(audit.acciones()) or "ninguna"))
            return 0
    else:
        print("\n".join(lineas))

    if not args.follow:
        return 0
    print("\n-- en vivo (Ctrl+C para salir) --", flush=True)
    vistas = set(lineas)
    try:
        while True:
            _t.sleep(1.0)
            for ln in leer(200):
                if ln not in vistas:
                    print(ln, flush=True)
                    vistas.add(ln)
    except KeyboardInterrupt:
        print("\n-- fin --")
    return 0


def _entrada_log(ln: str) -> dict:
    """Parte una línea del registro en {ts, accion, mensaje} (best-effort).
    Formato: 'YYYY-MM-DD HH:MM:SS accion    mensaje'."""
    ts = ln[:19]
    resto = ln[20:] if len(ln) > 20 else ""
    partes = resto.split(" ", 1)
    accion = partes[0] if partes else ""
    mensaje = partes[1].strip() if len(partes) > 1 else ""
    return {"ts": ts, "accion": accion, "mensaje": mensaje, "raw": ln}


def cmd_pause(args) -> int:
    """Pausa o reanuda la memoria (modo 'no recordar'). En pausa no se graban recuerdos
    nuevos ni se refuerzan los existentes; LEER sigue funcionando y no se borra nada."""
    from .config import set_paused
    quiere = not (args.cmd == "resume" or getattr(args, "off", False))
    estado = set_paused(quiere)
    forzado = os.environ.get("HIPERCAMPO_PAUSED", "") not in ("", "0", "false", "False")
    salida: dict[str, Any] = {"paused": estado}
    if forzado and not quiere:
        salida["aviso"] = ("HIPERCAMPO_PAUSED está fijada en el entorno y manda por "
                           "encima del interruptor: sigue en pausa hasta quitarla.")
    print(json.dumps(salida, ensure_ascii=False))
    return 0


def cmd_tokens(_args) -> int:
    """La FACTURA de tokens, en JSON: el rasgo de la casa hecho visible. Cuánto ha
    costado la memoria, cuánto se ahorró el presupuesto, y una serie temporal para
    dibujarla. Siempre es ESTIMACIÓN y se dice (el tokenizador de Claude no es público)."""
    from . import audit, budget
    from .config import db_path
    audit.set_logfile(db_path())
    resumen = audit.coste_tokens()
    resumen["presupuesto_hook"] = budget.HOOK_BUDGET
    resumen["presupuesto_identidad"] = budget.IDENTITY_BUDGET
    resumen["estimado"] = True
    resumen["metodo"] = budget.metodo()
    # serie temporal: cada inyección con su coste (para el gráfico del visor)
    serie = []
    for e in (_entrada_log(ln) for ln in audit.tail(0, accion="tokens")):
        m = re.search(r"(\d+) tok", e["mensaje"])
        if m:
            serie.append({"ts": e["ts"], "tok": int(m.group(1)),
                          "etiqueta": e["mensaje"].split(" ", 1)[0]})
    print(json.dumps({"summary": resumen, "series": serie[-200:]},
                     ensure_ascii=False, default=str))
    return 0


def cmd_status(_args) -> int:
    """Estado de salud en JSON para el visor: CLI, base de datos, servidor MCP y
    registro. Es el 'panel de control' de la memoria, sin adornos: dice qué vive."""
    from . import __version__, audit
    from .config import db_path, paused
    from .procs import listar
    ruta = os.path.abspath(db_path())
    out: dict[str, Any] = {"version": __version__, "python": sys.version.split()[0],
                           "paused": paused(), "db": {"path": ruta}}

    try:
        out["db"]["exists"] = os.path.isfile(ruta)
        out["db"]["size"] = os.path.getsize(ruta) if os.path.isfile(ruta) else 0
        carpeta = os.path.dirname(ruta) or "."
        out["db"]["writable"] = os.access(carpeta, os.W_OK)
    except OSError as e:
        out["db"]["error"] = str(e)

    try:
        hc = _hc()
        try:
            salud = hc.store.health(full=False)
            out["db"]["schema"] = hc.store.db.execute("PRAGMA user_version").fetchone()[0]
            out["db"]["schema_expected"] = hc.store.SCHEMA_VERSION
            out["db"]["healthy"] = bool(salud.get("sana"))
            out["db"]["integrity"] = salud.get("integridad")
            # Recuento de TODO el fichero (no solo el contexto actual), para que
            # cuadre con lo que enseña el visor ("todos los contextos").
            todos = hc.store.dump(all_namespaces=True, include_dormant=True)
            por_ctx: dict[str, int] = {}
            for m in todos:
                por_ctx[m["namespace"]] = por_ctx.get(m["namespace"], 0) + 1
            out["stats"] = {
                "total": len(todos),
                "episodicos_activos": sum(1 for m in todos if m["kind"] == "episodic"
                                          and not m["dormant"] and not m["consolidated"]),
                "semanticos": sum(1 for m in todos if m["kind"] == "semantic"),
                "latentes": sum(1 for m in todos if m["dormant"]),
                "archivados": sum(1 for m in todos if m["consolidated"]),
                "por_contexto": por_ctx,
                "tokens": hc.stats().get("tokens"),
            }
        finally:
            hc.close()
    except Exception as e:
        out["db"]["error"] = str(e)

    # Servidor MCP: en marcha o no (el cliente lo arranca al usar una herramienta).
    try:
        procesos = listar()
        out["mcp"] = {"running": len(procesos), "servers": procesos}
    except Exception as e:
        out["mcp"] = {"error": str(e)}

    # Registro (hooks y decisiones): activo, ruta y última actividad (señal de vida).
    audit.set_logfile(db_path())
    log = audit.logfile()
    reg: dict[str, Any] = {"enabled": bool(log), "path": log}
    if log and os.path.isfile(log):
        reg["last_activity"] = os.path.getmtime(log)
        reg["size"] = os.path.getsize(log)
    out["log"] = reg

    print(json.dumps(out, ensure_ascii=False, default=str))
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
        hc.close()
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
    sub.add_parser("hook", help="modo sináptico: para los hooks de Claude Code")
    sub.add_parser("identity", help="qué se ha aprendido trabajando")
    sub.add_parser("servers", help="qué servidores MCP hay en marcha y desde cuándo")
    rs = sub.add_parser("restart", help="reiniciar los servidores tras actualizar")
    rs.add_argument("--dry-run", action="store_true",
                    help="enseñar qué se cerraría, sin cerrar nada")
    rs.add_argument("--pids", help="cerrar SOLO estos pids (separados por comas); "
                                   "por defecto, todos")
    bg = sub.add_parser("budget", help="ver o fijar el presupuesto de tokens del hook")
    bg.add_argument("--set", type=int, help="fijar el presupuesto (tokens por turno)")
    bg.add_argument("--reset", action="store_true", help="volver al de fábrica (350)")
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
    rc = sub.add_parser("reclassify", help="mover recuerdos PROPIOS a otro contexto (curación)")
    rc.add_argument("--ids", required=True, help="ids separados por comas")
    rc.add_argument("--to", required=True, help="contexto destino")
    rc.add_argument("--namespace", help="contexto origen (por defecto el del entorno)")
    dm2 = sub.add_parser("dream", help="proponer PUENTES entre recuerdos distantes (ideas)")
    dm2.add_argument("--json", action="store_true", help="salida JSON (para el visor)")
    dm2.add_argument("--max", type=int, default=8, help="cuántas hipótesis como mucho")
    bk = sub.add_parser("backup", help="copia de seguridad consistente")
    bk.add_argument("dest", nargs="?")
    ls = sub.add_parser("list", help="volcar las memorias (tabla o --json para la UI)")
    ls.add_argument("--json", action="store_true", help="salida JSON (para el visor)")
    ls.add_argument("--all-namespaces", "-A", action="store_true",
                    help="todo el fichero, no solo el contexto actual")
    ls.add_argument("--namespace", help="ver un contexto concreto (por defecto: el actual)")
    ls.add_argument("--include-dormant", action="store_true",
                    help="incluir los latentes (olvidados-pero-no-borrados)")
    ls.add_argument("--kind", help="filtrar por tipo: episodic, semantic…")
    ls.add_argument("--sort", default="recent",
                    choices=("recent", "importance", "access", "created"),
                    help="orden (por defecto: acceso más reciente)")
    ls.add_argument("--limit", type=int, help="cuántas como mucho")
    gr = sub.add_parser("graph", help="volcar el grafo (nodos + aristas) para el visor")
    gr.add_argument("--all-namespaces", "-A", action="store_true")
    gr.add_argument("--namespace", help="contexto (por defecto: el actual)")
    gr.add_argument("--include-dormant", action="store_true", default=True)
    sub.add_parser("status", help="estado de salud en JSON (CLI, BD, MCP, registro)")
    pa = sub.add_parser("pause", help="PAUSAR la memoria: deja de grabar (modo 'no recordar')")
    pa.add_argument("--off", action="store_true", help="reanudar en vez de pausar")
    sub.add_parser("resume", help="reanudar la memoria tras una pausa")
    tk = sub.add_parser("tokens", help="factura de tokens en JSON (para el visor)")
    tk.add_argument("--json", action="store_true", default=True, help=argparse.SUPPRESS)
    dm = sub.add_parser("dormant", help="adormecer o despertar recuerdos por id")
    dm.add_argument("--ids", required=True, help="ids separados por comas")
    dm.add_argument("--wake", action="store_true", help="despertar en vez de adormecer")
    dm.add_argument("--namespace", help="contexto (por defecto: el actual)")
    pg = sub.add_parser("purge", help="borrado FÍSICO y seguro (secretos, RGPD, espacio)")
    pg.add_argument("--ids", help="ids concretos a borrar, separados por comas")
    pg.add_argument("--older-than", type=float, metavar="DÍAS",
                    help="purga los LATENTES sin acceso desde hace más de N días")
    pg.add_argument("--no-vacuum", action="store_true",
                    help="no recuperar espacio (más rápido; el texto igual se sobrescribe)")
    pg.add_argument("--namespace", help="contexto (por defecto: el actual)")
    pg.add_argument("--yes", action="store_true", help="no pedir confirmación")
    lg = sub.add_parser("log", help="qué ha decidido hipercampo últimamente")
    lg.add_argument("-n", type=int, default=20, help="cuántas líneas (0 = todas)")
    lg.add_argument("-f", "--follow", action="store_true",
                    help="quedarse mirando en vivo (Ctrl+C para salir)")
    lg.add_argument("-g", "--grep", metavar="TEXTO",
                    help="solo las líneas que contengan esto (ignora acentos)")
    lg.add_argument("-a", "--accion", metavar="ACCION",
                    help="solo esa acción: recall, remember, sleep, dream, ERROR…")
    lg.add_argument("--hoy", action="store_true", help="solo lo de hoy")
    lg.add_argument("--errores", action="store_true", help="atajo para --accion ERROR")
    lg.add_argument("--ruta", action="store_true", help="solo decir dónde está el fichero")
    lg.add_argument("--json", action="store_true", help="salida JSON (para el visor)")
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
    if args.cmd == "identity":
        return cmd_identity(args)
    if args.cmd == "servers":
        return cmd_servers(args)
    if args.cmd == "restart":
        return cmd_restart(args)
    if args.cmd == "budget":
        return cmd_budget(args)
    if args.cmd == "reclassify":
        return cmd_reclassify(args)
    if args.cmd == "dream":
        return cmd_dream(args)
    if args.cmd == "backup":
        from .backup import backup
        print("Copia creada en:", backup(args.dest)); return 0
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "graph":
        return cmd_graph(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "tokens":
        return cmd_tokens(args)
    if args.cmd in ("pause", "resume"):
        return cmd_pause(args)
    if args.cmd == "dormant":
        return cmd_dormant(args)
    if args.cmd == "purge":
        return cmd_purge(args)
    if args.cmd == "log":
        return cmd_log(args)

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
        hc.close()


if __name__ == "__main__":
    raise SystemExit(main())
