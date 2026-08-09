"""
DECISION LOG tests—the transparency contract.

A memory that decides whether to store, forget, or abstain must explain itself.
If this log breaks, hipercampo silently becomes a black box. Its hard rule is that
**observation must never break the observed operation**.

Run: python tests/support/test_audit.py
"""

import importlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests, clean               # noqa: E402


def _audit_activo(tmp: str):
    """Reload the module with logging ENABLED and pointed at `tmp`."""
    import os
    os.environ["HIPERCAMPO_LOG"] = "1"
    from hipercampo.support import audit
    importlib.reload(audit)
    Path(tmp).parent.mkdir(parents=True, exist_ok=True)
    Path(_LOG).unlink(missing_ok=True)          # cada test parte de un registro limpio
    audit.set_logfile(tmp)
    return audit


# Carpeta propia: el registro vive junto a la BD, así que compartir carpeta con
# otras suites mezclaría sus líneas con las nuestras y los asertos medirían ruido.
_DIR = Path("data/_t_audit")
_DB = str(_DIR / "audit.db")
_LOG = str(_DIR / "hipercampo.log")


def test_records_decision_with_its_numbers():
    audit = _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    audit.log("remember", "guardado id=7", novedad=0.42, sorpresa=0.81)
    lineas = audit.tail(5)
    assert lineas and "remember" in lineas[-1], lineas
    assert "novedad=0.42" in lineas[-1] and "sorpresa=0.81" in lineas[-1], lineas[-1]
    Path(_LOG).unlink(missing_ok=True)


def test_omits_empty_fields():
    """A log full of x=None fields is distracting noise."""
    audit = _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    audit.log("forget", "nada que podar", podados=0, evictado=None, motivo="")
    linea = audit.tail(1)[0]
    assert "evictado" not in linea and "motivo" not in linea, linea
    assert "podados=0" in linea, "un cero SÍ es información"
    Path(_LOG).unlink(missing_ok=True)


def test_disabling_really_disables_it():
    import os
    os.environ["HIPERCAMPO_LOG"] = "0"
    from hipercampo.support import audit
    importlib.reload(audit)
    Path(_LOG).unlink(missing_ok=True)
    audit.set_logfile(_DB)
    audit.log("remember", "esto no debe aparecer en ningun sitio")
    assert audit.logfile() is None, "con HIPERCAMPO_LOG=0 no debe haber fichero"
    assert audit.tail(5) == []
    assert not Path(_LOG).exists(), "escribió pese a estar desactivado"
    os.environ["HIPERCAMPO_LOG"] = "1"


def test_observation_never_breaks_observed_operation():
    """Logging swallows its own disk, permission, and formatting failures."""
    audit = _audit_activo(_DB)

    class Explosivo:
        def __repr__(self):
            raise RuntimeError("no me puedes registrar")
        __str__ = __repr__

    audit.log("recall", "con un campo que explota al formatearse", raro=Explosivo())

    audit._PATH = Path("Z:/ruta/imposible/hipercampo.log")   # destino inescribible
    audit.log("remember", "esto no se puede escribir en ningun disco")
    audit._PATH = None
    assert audit.tail(3) == [], "sin fichero, tail devuelve vacío sin reventar"


def test_piped_output_uses_utf8():
    """The MCP client reads stderr as UTF-8, so accented text must remain intact."""
    audit = _audit_activo(_DB)
    crudo = io.BytesIO()

    class TuberiaFalsa:
        """Como stderr cuando cuelga de una tubería: tiene .buffer y no es tty."""
        encoding = "cp1252"
        buffer = crudo

        def isatty(self):
            return False

        def write(self, _s):
            raise AssertionError("debió escribir bytes en .buffer, no texto")

        def flush(self):
            pass

    original = sys.stderr
    sys.stderr = TuberiaFalsa()
    try:
        audit.log("recall", "abstención: nada destaca del ruido")
    finally:
        sys.stderr = original
    bytes_escritos = crudo.getvalue()
    assert "abstención".encode() in bytes_escritos, (
        f"no salió en UTF-8: {bytes_escritos!r}")
    Path(_LOG).unlink(missing_ok=True)


def test_real_cycle_leaves_readable_trace():
    """End to end, remember and recall must appear in the log."""
    _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    from hipercampo.support import audit
    from hipercampo.cycle.memory import Hipercampo
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)

    hc = Hipercampo(_DB, namespace="test")
    hc.remember("el amoniaco hierve a menos treinta y tres grados", 0.7)
    hc.recall("a que temperatura hierve el amoniaco")
    hc.store.close()

    texto = "\n".join(audit.tail(50))
    assert "remember" in texto and "recall" in texto, texto
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    Path(_LOG).unlink(missing_ok=True)


def test_log_filters():
    audit = _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    audit.log("recall", "abstención: nada destaca del ruido", n=18)
    audit.log("remember", "guardado id=1", texto="el diseño de Peñíscola")
    audit.log("ERROR", "recall: base de datos bloqueada")

    assert len(audit.tail(0, action="recall")) == 1, "filtro por acción"
    assert len(audit.tail(0, action="ERROR")) == 1, "los errores se filtran igual"
    # buscar sin acentos debe encontrar CON acentos: nadie escribe 'diseño' al buscar
    assert len(audit.tail(0, contains="diseno")) == 1, "búsqueda insensible a acentos"
    assert len(audit.tail(0, contains="ABSTENCION")) == 1, "insensible a mayúsculas"
    assert audit.tail(0, contains="no aparece jamas") == []
    assert len(audit.tail(0, today_only=True)) == 3, "todo esto es de hoy"
    assert set(audit.actions()) == {"recall", "remember", "ERROR"}, audit.actions()
    Path(_LOG).unlink(missing_ok=True)


def test_log_explains_why_not_only_what():
    """A log saying only 'abstention' without its comparison explains nothing."""
    _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    from hipercampo.support import audit
    from hipercampo.cycle.memory import Hipercampo
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)

    hc = Hipercampo(_DB, namespace="test")
    hc.remember("el amoniaco hierve a menos treinta y tres grados", 0.7)
    hc.recall("a que temperatura hierve el amoniaco")
    hc.close()

    texto = "\n".join(audit.tail(50))
    for dato in ("novelty=", "surprise=", "scanned=", "best=", "ms="):
        assert dato in texto, f"falta {dato} en el registro:\n{texto}"
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    Path(_LOG).unlink(missing_ok=True)


# --- one entry per line, whatever the user wrote ----------------------------
def test_a_newline_in_the_text_does_not_split_the_entry():
    """The log records fragments of what the user wrote. A memory containing a
    line break used to split its entry in two, and the orphaned half — no
    timestamp, no action — came back from `tail` as an entry of its own, which the
    viewer rendered as a "?" row. Found in a real log: two of them."""
    audit = _audit_activo(_LOG)
    audit.log("remember", "first line\nsecond line", text="a\nb\tc")
    lines = audit.tail(0)
    assert len(lines) == 1, f"the entry was split across {len(lines)} lines: {lines}"
    assert "first line second line" in lines[0], lines[0]
    assert "a b c" in lines[0], lines[0]


def test_orphan_lines_in_an_older_log_are_ignored():
    """The log is append-only, so a file written before the fix still holds
    orphaned lines. Reading is where they are filtered out; otherwise the viewer
    keeps showing "?" rows for entries that do not exist."""
    audit = _audit_activo(_LOG)
    audit.log("recall", "a well-formed entry")
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write("an orphaned continuation line with no timestamp\n\n")
    lines = audit.tail(0)
    assert len(lines) == 1, lines
    assert "well-formed" in lines[0], lines[0]


def test_the_bill_counts_tokens_and_not_clock_seconds():
    """Every entry here begins "YYYY-MM-DD HH:MM:SS tokens ", so searching the
    whole line for `(\\d+) tok` matched "07 tok" — the SECONDS of the clock
    followed by the action column — and never reached the real figure. Measured on
    a real log: it reported 5304 tokens where the true total was 65451, a 12x
    under-count of the one number this project uses to argue for itself.

    The tell was there all along: the viewer's chart reads the message and was
    right, while the summary above it read the whole line and was wrong, on the
    same data in the same panel."""
    audit = _audit_activo(_LOG)
    audit.log("tokens", "injected 350 tok")
    cost = audit.token_cost()
    assert cost["total"] == 350, f"counted {cost['total']}, probably the seconds"


def test_the_savings_counter_reads_both_spellings():
    """`token_cost` matched "(de N)" while the hook had started writing "(of N)"
    after the translation, so the savings counter silently reported zero. A real
    log spans the change, so both are accepted: 10049 tokens had gone uncounted."""
    audit = _audit_activo(_LOG)
    audit.log("tokens", "injected 100 tok (of 250, budget 350)")
    audit.log("tokens", "injected 100 tok (de 250)")
    saved = audit.token_cost()["saved_by_budget"]
    assert saved == 300, f"expected 150 per line, got {saved}"


if __name__ == "__main__":
    clean()
    codigo = run_tests(dict(globals()))
    Path(_LOG).unlink(missing_ok=True)
    sys.exit(codigo)
