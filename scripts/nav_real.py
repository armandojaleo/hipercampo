"""
Validación en corpus REAL (no sintético) del grafo navegable.

El benchmark de escala (`nav_scale.py`) usa clústeres sintéticos a similitud ~0.99:
trivialmente separables. Aquí se valida sobre TEXTO real y difuso —docstrings de la
librería estándar de Python, agrupados por módulo (categoría con verdad)—, offline y
reproducible en cualquier máquina. La pregunta honesta: ¿el titular de b12 (navegar
recupera como escanear, tocando poco) aguanta fuera del banco sintético?

Mide, sobre el MISMO camino de producción (store.reindex_navgraph + store.navgraph +
graph.search_with_stats):
  - FIDELIDAD del índice: recall@5 de navegar vs escaneo completo (la verdad),
  - %visitado y latencia (la sublinealidad),
  - precisión de GRUPO@5: navegar y escaneo (calidad semántica; será baja en léxico,
    y ese es justo el cuello de botella conocido de los sinónimos).

Ejecuta:  python scripts/nav_real.py
"""

import importlib
import inspect
import statistics
import sys
import time
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.encoder import encode_text          # noqa: E402
from hipercampo.store import Store                    # noqa: E402
from hipercampo.vsa import similarity_batch           # noqa: E402

DB = "data/_nav_real.db"
MODULOS = ["email", "http", "json", "math", "random", "os", "xml", "unittest",
           "logging", "sqlite3", "statistics", "argparse", "collections", "asyncio",
           "socket", "decimal", "datetime", "threading", "hashlib", "urllib",
           "html", "csv", "configparser", "tarfile", "zipfile", "ftplib", "smtplib"]


def clean() -> None:
    for suf in ("", "-wal", "-shm"):
        Path(DB + suf).unlink(missing_ok=True)


def cosechar() -> tuple[list[str], list[int], list[str]]:
    """Docstrings reales, etiquetados por módulo. Recorre submódulos para tener volumen."""
    textos, etiqueta, nombres = [], [], []
    vistos: set[str] = set()
    for lbl, raiz in enumerate(MODULOS):
        try:
            mod = importlib.import_module(raiz)
        except Exception:
            continue
        # Solo miembros de primer nivel: importar submódulos por pkgutil puede ejecutar
        # código (p.ej. unittest.__main__ corre tests). Con clases y funciones del módulo
        # basta para tener texto real y volumen suficiente, sin efectos secundarios.
        for _, obj in inspect.getmembers(mod):
            try:
                doc = inspect.getdoc(obj)
                miembros = inspect.getmembers(obj) if inspect.isclass(obj) else []
            except Exception:
                doc, miembros = None, []
            candidatos = [doc] + [inspect.getdoc(o) for _, o in miembros[:40]]
            for d in candidatos:
                if not d or len(d) < 80:
                    continue
                d = " ".join(d.split())[:400]
                if d in vistos:
                    continue
                vistos.add(d)
                textos.append(d)
                etiqueta.append(lbl)
                nombres.append(raiz)
    return textos, etiqueta, nombres


def main() -> None:
    textos, etiqueta, nombres = cosechar()
    n = len(textos)
    etiqueta = np.array(etiqueta)
    print(f"Corpus REAL: {n} docstrings de {len(set(nombres))} módulos "
          f"(categoría = módulo)")
    reparto = {nombres[i]: 0 for i in range(n)}
    for nm in nombres:
        reparto[nm] += 1
    print("reparto:", {k: v for k, v in sorted(reparto.items(), key=lambda x: -x[1])[:8]}, "…")

    clean()
    store = Store(DB, namespace="real")
    t0 = time.perf_counter()
    # Capturamos el id que devuelve add(): así ids[i] <-> codes[i] <-> mat[i] <->
    # etiqueta[i] quedan ALINEADOS. (Antes ids salía de store.all() en otro orden, y la
    # comparación mezclaba dos sistemas de coordenadas -> fidelidad ~0 artificial.)
    codes, ids = [], []
    with store.transaction():
        for txt in textos:
            hv = encode_text(txt)
            mid = store.add(txt, hv, 1.0, 0.5, 0.6)
            codes.append(hv)
            ids.append(mid)
    mat = np.frombuffer(b"".join(c.tobytes() for c in codes),
                        dtype=np.uint8).reshape(n, 1250)
    id_a_pos = {mid: i for i, mid in enumerate(ids)}
    print(f"sembrado+codificado: {time.perf_counter() - t0:.1f}s")

    store.reindex_navgraph(M=12)                       # camino de producción (knn)
    graph = store.navgraph(shortcuts=2)                # índice navegable real

    # consultas: 40 docstrings al azar como 'pista'; verdad = escaneo completo
    rng = np.random.default_rng(7)
    sample = rng.choice(n, size=min(40, n), replace=False)

    fidelidad, grupo_nav, grupo_scan, lat, vis = [], [], [], [], []
    for qi in sample:
        qi = int(qi)
        q, qid, lbl = codes[qi], ids[qi], etiqueta[qi]
        sims = similarity_batch(q, mat)
        orden = [int(p) for p in np.argsort(sims)[::-1] if int(p) != qi][:5]
        scan_ids = {ids[p] for p in orden}             # verdad, por id de BD
        t = time.perf_counter()
        found, visited = graph.search_with_stats(q, k=6, ef=48)
        lat.append((time.perf_counter() - t) * 1000)
        vis.append(visited)
        nav_ids = [mid for mid, _ in found if mid != qid][:5]
        # FIDELIDAD: ¿navegar trae los mismos que el escaneo? (todo por id de BD)
        fidelidad.append(len(set(nav_ids) & scan_ids) / 5.0)
        # PRECISIÓN DE GRUPO: ¿comparten módulo con la consulta?
        grupo_nav.append(np.mean([etiqueta[id_a_pos[m]] == lbl
                                  for m in nav_ids if m in id_a_pos]) if nav_ids else 0.0)
        grupo_scan.append(np.mean([etiqueta[p] == lbl for p in orden]))
    store.close()
    clean()

    print("\n=== VEREDICTO en corpus REAL ===")
    print(f"fidelidad nav vs escaneo (recall@5): {statistics.mean(fidelidad):.3f}")
    print(f"latencia navegable: p50={statistics.median(lat):.2f}ms "
          f"p95={sorted(lat)[int(0.95 * len(lat))]:.2f}ms")
    print(f"visitados: {statistics.mean(vis):.0f} de {n} "
          f"({100 * statistics.mean(vis) / n:.1f}%)")
    print(f"precisión de grupo@5 — navegar: {statistics.mean(grupo_nav):.3f} · "
          f"escaneo: {statistics.mean(grupo_scan):.3f}")
    print("\nNota: la precisión de grupo mide CALIDAD semántica (léxica aquí); baja es "
          "esperable y marca el cuello de sinónimos. La FIDELIDAD mide el ÍNDICE: si es "
          "alta, navegar ≈ escanear también en texto real, no solo en el banco sintético.")


if __name__ == "__main__":
    main()
