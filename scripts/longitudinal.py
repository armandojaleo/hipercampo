"""
LONGITUDINAL experiment — evidence-phase demonstration #2 (see paper/OUTLINE.md).

Simulate MONTHS in an agent memory with a SIMULATED CLOCK (patching time.time to
compress time). Measure whether hipercampo's cognitive features—temporally valid facts,
active forgetting with retention, and abstention—produce a more useful memory per MB:
temporally correct, low in false recall, forgetting noise while keeping valuable facts.

House rule: generator and metrics FIRST—measure before believing. The 1M run comes
later; this validates that metrics are computable and informative at modest scale.
Compare with a naive BASELINE that stores everything as text and answers with top-1
recall, without temporal validity or forgetting: the typical "vector store" pattern.

Usage:
  python scripts/longitudinal.py                       # modest run + summary
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

from hipercampo.support import audit, config                       # noqa: E402
from hipercampo.cycle import memory
from hipercampo.cycle.memory import Hipercampo                            # noqa: E402

DAY = 86400.0
BASE_EPOCH = 1_600_000_000.0          # Fixed, reproducible starting point.

# --- simulated clock: the engine reads time.time(), so patching compresses months ----
_CLOCK = [BASE_EPOCH]
_REAL_TIME = time.time
def _set_clock(t): _CLOCK[0] = t
def _patch_clock(): time.time = lambda: _CLOCK[0]
def _unpatch_clock(): time.time = _REAL_TIME


def build_stream(rng, cfg):
    """Generate an event stream labeled with temporal ground truth."""
    horizon = cfg["months"] * 30 * DAY
    events = []                        # (t, kind, payload)
    gt = {}                            # entity -> sorted [(t, value), ...]

    # 1) ENTITIES with an attribute that CHANGES over time (contradictions, expiry).
    for i in range(cfg["entities"]):
        subj, pred = f"entidad{i}", "estado"
        n_changes = rng.randint(1, cfg["max_changes"])
        ts = sorted(rng.uniform(0, horizon) for _ in range(n_changes))
        timeline = []
        for k, t in enumerate(ts):
            val = f"s{i}v{k}"          # Distinctive value (unique token).
            events.append((BASE_EPOCH + t, "fact", (subj, pred, val)))
            timeline.append((BASE_EPOCH + t, val))
        gt[(subj, pred)] = timeline

    # 2) Low-value routine NOISE (should be forgotten).
    for j in range(cfg["noise"]):
        t = BASE_EPOCH + rng.uniform(0, horizon)
        events.append((t, "noise", f"noise{j} rutina {rng.randint(0, 9999)}"))

    # 3) High-value RARE episodes (should survive forgetting).
    for j in range(cfg["rare"]):
        t = BASE_EPOCH + rng.uniform(0, horizon)
        events.append((t, "rare", f"rare{j} incidente critico {rng.randint(0, 9999)}"))

    # 4) RESURFACING: low-value memories planted EARLY so they fade, each with a unique
    # CUE. At the end, feed that cue to muse and see whether dormant memories return.
    for j in range(cfg["resurf"]):
        t = BASE_EPOCH + rng.uniform(0, horizon * 0.1)
        events.append((t, "resurf", f"resurf{j} zzq{j}"))

    events.sort(key=lambda e: e[0])

    # Temporal PROBES: (entity, t) at a random instant; expected value is valid at t.
    probes = []
    keys = list(gt.keys())
    for _ in range(cfg["probes"]):
        key = rng.choice(keys)
        t = BASE_EPOCH + rng.uniform(0, horizon)
        probes.append((key, t, _valid_at(gt[key], t)))

    # ABSENT: novel subject AND predicate, never stored, so they should trigger abstention.
    # Sharing a predicate is insufficient because fact matching uses the known set.
    absent = [(f"fantasma{i}", f"atributo{i}") for i in range(cfg["absent"])]
    return events, gt, probes, absent, horizon


def _valid_at(timeline, t):
    """Return the value valid at t: the last change with t_i <= t, else None."""
    val = None
    for ti, vi in timeline:
        if ti <= t:
            val = vi
        else:
            break
    return val


def run_world(events, cfg, horizon, mode):
    """Run one world (full=hipercampo, naive=baseline) over the SAME stream."""
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
                else:                         # Naive: every version coexists as text.
                    hc.remember(f"{subj} {pred} {val}", importance=0.6, confidence=0.7)
            elif kind == "noise":
                hc.remember(payload, importance=0.15, confidence=0.3)
            elif kind == "resurf":
                hc.remember(payload, importance=0.2, confidence=0.3)
            else:                              # rare
                hc.remember(payload, importance=0.9, confidence=0.9)
            # Monthly forgetting cycles, only in the cognitive world.
            if mode == "full" and t >= next_forget:
                hc.forget()
                next_forget += 30 * DAY
        _set_clock(BASE_EPOCH + horizon + 7 * DAY)   # One week after the last event.
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

    # --- temporal correctness: only the temporally aware world can answer this ---
    if mode == "full":
        ok = 0
        for (subj, pred), t, expected in probes:
            r = hc.ask_role("object", {"subject": subj, "predicate": pred}, at=t)
            got = r.get("answer")
            if (expected is None and got is None) or (got == expected):
                ok += 1
        out["temporal_correctness"] = round(ok / len(probes), 3) if probes else None
    else:
        out["temporal_correctness"] = None    # A vector store does not model time.

    # --- correct CURRENT value and CONTRADICTION rate (returning expired truth) ---
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

    # --- false recall: queries for ABSENT entities should cause abstention ---
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

    # --- forgetting quality: noise should become dormant while rare facts stay awake ---
    rows = hc.store.dump(all_namespaces=False, include_dormant=True)
    noise = [r for r in rows if r["text"].startswith("noise")]
    rare = [r for r in rows if r["text"].startswith("rare")]
    nd = sum(1 for r in noise if r["dormant"])
    rk = sum(1 for r in rare if not r["dormant"])
    out["forgetting"] = {
        "noise_dormant_rate": round(nd / len(noise), 3) if noise else None,
        "valuable_kept_rate": round(rk / len(rare), 3) if rare else None,
    }

    # --- resurfacing: forgotten memories return when their cue appears through muse ---
    # Only the world that FORGETS needs resurfacing; naive never lost them (n/a).
    if mode == "full":
        resurf = [r for r in rows if r["text"].startswith("resurf")]
        dormidos = [r for r in resurf if r["dormant"]]
        base = dormidos or resurf                      # Forgotten subset, or all as fallback.
        vueltos = 0
        for r in base:
            cue = r["text"].split()[1]                 # Unique cue (zzqN).
            got = hc.muse(cue, k=3)
            if any(cue in h.get("text", "") for h in got):
                vueltos += 1
        out["resurfacing"] = {
            "dormant_rate": round(len(dormidos) / len(resurf), 3) if resurf else None,
            "resurfaced_rate": round(vueltos / len(base), 3) if base else None,
        }
    else:
        out["resurfacing"] = {"dormant_rate": None, "resurfaced_rate": None}

    # --- footprint: total disk bytes + signal/noise (awake / total). Do NOT use
    # "bytes per useful memory": forgetting makes memories DORMANT, not deleted, so
    # dormant data remains on disk and that ratio would punish effective forgetting.
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
    ap.add_argument("--resurf", type=int, default=25)
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--max-changes", type=int, default=4)
    ap.add_argument("--probes", type=int, default=300)
    ap.add_argument("--absent", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cfg = {"entities": a.entities, "noise": a.noise, "rare": a.rare, "resurf": a.resurf,
           "months": a.months, "max_changes": a.max_changes, "probes": a.probes,
           "absent": a.absent, "seed": a.seed}
    report = run(cfg)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2)); return
    f, nv = report["full"], report["naive"]
    print(f"LONGITUDINAL · {report['events']} events · {cfg['months']} simulated months "
          f"· {cfg['entities']} entities · {cfg['noise']} noise items")
    print("-" * 62)
    def s(x):
        return "n/a" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))

    def row(name, k, sub=None, better="?", note=""):
        fv = f[k] if sub is None else f[k][sub]
        nvv = nv[k] if sub is None else nv[k][sub]
        print(f"{name:<24}{s(fv):>12}{s(nvv):>10}   {better:<4} {note}")
    print(f"{'':<24}{'hiper':>12}{'naive':>10}        meaning")
    row("contradiction", "contradiction_rate", None, "↓", "returns EXPIRED truth")
    row("current accuracy", "current_correctness", None, "↑", "knows what is true NOW")
    row("temporal accuracy", "temporal_correctness", None, "↑", "truth IN THE PAST")
    row("false recall", "false_recall", None, "↓", "answers what it does not know")
    row("forgotten noise", "forgetting", "noise_dormant_rate", "↑", "drops low-value noise")
    row("valuable retained", "forgetting", "valuable_kept_rate", "↑", "keeps what matters")
    row("resurfacing", "resurfacing", "resurfaced_rate", "↑", "a cue revives forgotten data")
    row("awake ratio", "footprint", "awake_ratio", "", "awake fraction (clean signal)")
    row("db bytes", "footprint", "db_bytes", "↓", "disk footprint")
    print("-" * 62)
    verdict = (f"Headline: hipercampo contradicts {f['contradiction_rate']:.0%} vs "
               f"{nv['contradiction_rate']:.0%} for naive; it knows 'now' "
               f"{f['current_correctness']:.0%} vs {nv['current_correctness']:.0%}, "
               f"and answers about the past (naive cannot).")
    print(verdict)


if __name__ == "__main__":
    main()
