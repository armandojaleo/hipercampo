"""
Experimento LONGITUDINAL — demostración #2 de la fase de evidencia (ver paper/OUTLINE.md).

Simula MESES de vida de una memoria de agente con un RELOJ SIMULADO (parchea time.time,
comprime el tiempo) y mide si las funciones cognitivas de hipercampo —hechos con validez
temporal, olvido activo con retención, abstención— producen una memoria más útil por MB,
correcta en el tiempo, con baja false recall, que olvida el ruido pero conserva lo valioso.

Regla de la casa: PRIMERO el generador y las métricas (medir antes de creer). El número a
1M vendrá después; esto valida que las métricas son computables y dan señal a escala modesta.
Se compara contra un BASELINE naive (guardar todo como texto, responder por recall top-1,
sin validez temporal ni olvido) — el patrón "vector store".

Uso:
  python scripts/longitudinal.py                       # corrida modesta + resumen
  python scripts/longitudinal.py --json
  python scripts/longitudinal.py --entities 200 --noise 3000 --months 12 --seed 7
"""
import argparse
import json
import os
import random
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows: cp1252 rompe ·
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hipercampo import audit, config, memory                       # noqa: E402
from hipercampo.memory import Hipercampo                            # noqa: E402

DAY = 86400.0
BASE_EPOCH = 1_600_000_000.0          # un punto de partida fijo y reproducible

# --- reloj simulado: todo el motor lee time.time(), así que parchearlo comprime meses ----
_CLOCK = [BASE_EPOCH]
_REAL_TIME = time.time
def _set_clock(t): _CLOCK[0] = t
def _patch_clock(): time.time = lambda: _CLOCK[0]
def _unpatch_clock(): time.time = _REAL_TIME


def build_stream(rng, cfg):
    """Genera un flujo de eventos etiquetado con su ground-truth temporal."""
    horizon = cfg["months"] * 30 * DAY
    events = []                        # (t, kind, payload)
    gt = {}                            # entidad -> [(t, valor), ...] ordenado

    # 1) ENTIDADES con un atributo que CAMBIA en el tiempo (contradicciones, caducidad).
    for i in range(cfg["entities"]):
        subj, pred = f"entidad{i}", "estado"
        n_changes = rng.randint(1, cfg["max_changes"])
        ts = sorted(rng.uniform(0, horizon) for _ in range(n_changes))
        timeline = []
        for k, t in enumerate(ts):
            val = f"s{i}v{k}"          # valor distintivo (token único)
            events.append((BASE_EPOCH + t, "fact", (subj, pred, val)))
            timeline.append((BASE_EPOCH + t, val))
        gt[(subj, pred)] = timeline

    # 2) RUIDO rutinario de bajo valor (debería olvidarse).
    for j in range(cfg["noise"]):
        t = BASE_EPOCH + rng.uniform(0, horizon)
        events.append((t, "noise", f"noise{j} rutina {rng.randint(0, 9999)}"))

    # 3) Episodios RAROS de alto valor (deberían sobrevivir al olvido).
    for j in range(cfg["rare"]):
        t = BASE_EPOCH + rng.uniform(0, horizon)
        events.append((t, "rare", f"rare{j} incidente critico {rng.randint(0, 9999)}"))

    events.sort(key=lambda e: e[0])

    # PROBES temporales: (entidad, t) en un instante aleatorio; valor esperado = el vigente en t.
    probes = []
    keys = list(gt.keys())
    for _ in range(cfg["probes"]):
        key = rng.choice(keys)
        t = BASE_EPOCH + rng.uniform(0, horizon)
        probes.append((key, t, _valid_at(gt[key], t)))

    # AUSENTES: sujeto Y predicado NOVEDOSOS (nunca guardados) -> deben provocar abstención.
    # (Compartir el predicado no vale: el emparejamiento de hechos casa por el conjunto conocido.)
    absent = [(f"fantasma{i}", f"atributo{i}") for i in range(cfg["absent"])]
    return events, gt, probes, absent, horizon


def _valid_at(timeline, t):
    """Valor vigente en el instante t (el del último cambio con t_i <= t; None si antes)."""
    val = None
    for ti, vi in timeline:
        if ti <= t:
            val = vi
        else:
            break
    return val


def run_world(events, cfg, horizon, mode):
    """Corre un 'mundo' (full=hipercampo, naive=baseline) sobre el MISMO flujo."""
    prev_gate = memory.GATE_ENABLED
    prev_auto = memory.AUTOSLEEP_EVERY
    audit._ENABLED = False
    memory.AUTOSLEEP_EVERY = 0
    memory.GATE_ENABLED = (mode == "full")
    config.paused = lambda: False
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    hc = Hipercampo(path, namespace="long")
    next_forget = BASE_EPOCH + 30 * DAY
    try:
        for t, kind, payload in events:
            _set_clock(t)
            if kind == "fact":
                subj, pred, val = payload
                if mode == "full":
                    hc.remember_fact({"subject": subj, "predicate": pred, "object": val},
                                     importance=0.6, confidence=0.7)
                else:                         # naive: cada versión es un texto que coexiste
                    hc.remember(f"{subj} {pred} {val}", importance=0.6, confidence=0.7)
            elif kind == "noise":
                hc.remember(payload, importance=0.15, confidence=0.3)
            else:                              # rare
                hc.remember(payload, importance=0.9, confidence=0.9)
            # ciclos mensuales de olvido (solo el mundo cognitivo)
            if mode == "full" and t >= next_forget:
                hc.forget()
                next_forget += 30 * DAY
        _set_clock(BASE_EPOCH + horizon + 7 * DAY)   # una semana después del último evento
        if mode == "full":
            hc.forget()
    finally:
        memory.GATE_ENABLED = prev_gate
        memory.AUTOSLEEP_EVERY = prev_auto
    return hc, path


def measure(hc, path, mode, gt, probes, absent, horizon):
    end_t = BASE_EPOCH + horizon + 7 * DAY
    _set_clock(end_t)
    out = {}

    # --- corrección temporal (solo el mundo con validez temporal responde a esto) ---
    if mode == "full":
        ok = 0
        for (subj, pred), t, expected in probes:
            r = hc.ask_role("object", {"subject": subj, "predicate": pred}, at=t)
            got = r.get("answer")
            if (expected is None and got is None) or (got == expected):
                ok += 1
        out["temporal_correctness"] = round(ok / len(probes), 3) if probes else None
    else:
        out["temporal_correctness"] = None    # el vector store no modela el tiempo

    # --- valor ACTUAL correcto y tasa de CONTRADICCIÓN (responder una verdad ya cerrada) ---
    correct = contradiction = miss = 0
    for (subj, pred), timeline in gt.items():
        current = timeline[-1][1]
        past = {v for _, v in timeline[:-1]}
        if mode == "full":
            got = hc.ask_role("object", {"subject": subj, "predicate": pred}).get("answer")
        else:
            hits = hc.recall(f"{subj} {pred}", k=1)
            got = hits[0]["text"].split()[-1] if hits else None
        if got == current:
            correct += 1
        elif got in past:
            contradiction += 1
        else:
            miss += 1
    n = len(gt)
    out["current_correctness"] = round(correct / n, 3)
    out["contradiction_rate"] = round(contradiction / n, 3)

    # --- false recall: preguntar por entidades AUSENTES, debe abstenerse ---
    answered = 0
    for subj, pred in absent:
        if mode == "full":
            got = hc.ask_role("object", {"subject": subj, "predicate": pred}).get("answer")
        else:
            hits = hc.recall(f"{subj} {pred}", k=1)
            got = hits[0]["text"].split()[-1] if hits else None
        if got is not None:
            answered += 1
    out["false_recall"] = round(answered / len(absent), 3) if absent else None

    # --- calidad de olvido: el ruido debe adormecer, lo raro seguir despierto ---
    rows = hc.store.dump(all_namespaces=False, include_dormant=True)
    noise = [r for r in rows if r["text"].startswith("noise")]
    rare = [r for r in rows if r["text"].startswith("rare")]
    nd = sum(1 for r in noise if r["dormant"])
    rk = sum(1 for r in rare if not r["dormant"])
    out["forgetting"] = {
        "noise_dormant_rate": round(nd / len(noise), 3) if noise else None,
        "valuable_kept_rate": round(rk / len(rare), 3) if rare else None,
    }

    # --- huella: bytes totales en disco + señal/ruido (despiertos / total). NO se usa
    # "bytes por útil": olvidar ADORMECE (no borra), así que los latentes siguen en disco
    # y esa ratio penalizaría precisamente al que sabe olvidar. El total sí es comparable.
    hc.store.commit()
    size = os.path.getsize(path)
    util = sum(1 for r in rows if not r["dormant"])
    out["footprint"] = {"db_bytes": size, "memories": len(rows), "dormant": len(rows) - util,
                        "awake_ratio": round(util / len(rows), 3) if rows else None}
    return out


def run(cfg):
    rng = random.Random(cfg["seed"])
    _patch_clock()
    try:
        events, gt, probes, absent, horizon = build_stream(rng, cfg)
        report = {"config": cfg, "events": len(events)}
        for mode in ("full", "naive"):
            hc, path = run_world(events, cfg, horizon, mode)
            report[mode] = measure(hc, path, mode, gt, probes, absent, horizon)
            hc.close()
            try: os.remove(path)
            except OSError: pass
    finally:
        _unpatch_clock()
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entities", type=int, default=120)
    ap.add_argument("--noise", type=int, default=1500)
    ap.add_argument("--rare", type=int, default=40)
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--max-changes", type=int, default=4)
    ap.add_argument("--probes", type=int, default=300)
    ap.add_argument("--absent", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cfg = {"entities": a.entities, "noise": a.noise, "rare": a.rare, "months": a.months,
           "max_changes": a.max_changes, "probes": a.probes, "absent": a.absent, "seed": a.seed}
    report = run(cfg)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2)); return
    f, nv = report["full"], report["naive"]
    print(f"LONGITUDINAL · {report['events']} eventos · {cfg['months']} meses simulados "
          f"· {cfg['entities']} entidades · {cfg['noise']} ruido")
    print(f"{'métrica':<26}{'hipercampo':>14}{'naive':>12}")
    print("-" * 52)
    def row(name, k, sub=None):
        fv = f[k] if sub is None else f[k][sub]
        nvv = nv[k] if sub is None else nv[k][sub]
        s = lambda x: "n/a" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
        print(f"{name:<26}{s(fv):>14}{s(nvv):>12}")
    row("temporal correctness", "temporal_correctness")
    row("current correctness", "current_correctness")
    row("contradiction rate", "contradiction_rate")
    row("false recall", "false_recall")
    row("noise forgotten", "forgetting", "noise_dormant_rate")
    row("valuable kept", "forgetting", "valuable_kept_rate")
    row("db bytes", "footprint", "db_bytes")
    row("awake ratio", "footprint", "awake_ratio")


if __name__ == "__main__":
    main()
