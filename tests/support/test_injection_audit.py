"""The injection audit has to read the cost the hook actually logged.

It reported "mean 30 tok" for months while real injections were ~300: it
only matched the old Spanish lines, and its regex read the timestamp's
seconds ("10:09:22 tokens") as the token count.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root

from scripts import injection_audit  # noqa: E402

# Exactly what audit.tail returns, both log languages.
_LINES = [
    "2026-07-23 09:49:51 tokens    inyectados 359 tok (de 647, presupuesto 350)",
    "2026-11-06 10:08:54 tokens    identity 498 tok (of 2661)",
    "2026-11-06 10:09:22 tokens    injected 312 tok",
    "2026-11-06 10:18:13 tokens    injected 353 tok (of 700, budget 350)",
]


def test_reads_injected_tokens_not_timestamp_seconds(monkeypatch):
    monkeypatch.setattr(injection_audit.audit, "tail",
                        lambda n=0, action=None, **kw: list(_LINES))
    cost = injection_audit.actual_cost()
    # Identity is a per-session cost, not a per-turn injection.
    assert cost["injections"] == 3
    assert cost["max"] == 359
    assert cost["mean"] == round((359 + 312 + 353) / 3)
