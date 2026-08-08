"""
Judgment-call parameters for the memory cycle — this is where human judgment
governs. Split out of `memory.py` because these constants (and the
abstention gate they feed) are the system's most delicate, most-measured
knobs, and `scripts/calibrate.py` needs to reach them without wading through
the rest of the cycle's code.

Import this module for the constants; call `abstention_gate` from `recall()`
and `creative_fit` from `dream()`.
"""

import os
from typing import Any

# Atomize on write: a long DOCUMENT with several ideas gets chunked and each
# atom is stored linked to its source, so a buried fact doesn't get diluted
# (1/sqrt(T), measured). Only documents, NOT notes: a short note is stored
# whole (atomizing it fragments it into meaningless chunks -"', queryable by
# role."- that clutter the memory). Dilution at a few sentences is mild
# (measured: +0.075 at 4 facts); the big jump is in long texts.
ATOMIZE_ON_REMEMBER = os.environ.get("HIPERCAMPO_NO_ATOMIZE") != "1"
ATOMIZE_MIN_LEN = int(os.environ.get("HIPERCAMPO_ATOMIZE_MIN_LEN", "500"))  # chars
ATOMIZE_MIN_ATOMS = 4    # and at least this many atoms: otherwise fragmenting doesn't pay off
NOVELTY_WRITE_THRESHOLD = 0.06   # below -> we already have it, don't duplicate
SURPRISE_WRITE_THRESHOLD = 0.05  # below -> the model already predicted it, trivial
SUPERSEDE_HINT_SIMILARITY = 0.72 # above -> we hint at a possible update
SUPERSEDED_RECALL_PENALTY = 0.2  # how much a superseded memory is demoted on recall
# CALIBRATED with scripts/calibrate.py on N=500 (30 positive queries, 30 unrelated).
# MIN_RECALL_SCORE turned out to be INERT: moving it from 0.03 to 0.08 changes the
# global MRR <=0.002 and the false-recall rate NOT AT ALL. Left where it was because
# it isn't the lever (the ROADMAP asked to calibrate this one; measurement says the
# one below is what actually governs).
MIN_RECALL_SCORE = 0.03          # floor PER ITEM: below this it's not included in the answer
# The real lever. It was at 0.08, BELOW the 5th percentile of unrelated queries
# (0.100): it wasn't a gate at all, it let through the entire negative
# distribution, hence falseRec 1.00. The classes DO separate at the median
# (positive 0.327 vs unrelated 0.160).
# There's a CLIFF at 0.195 and the value was chosen on the side that degrades
# smoothly:
#   floor   synonym  global  falseRec
#   0.190     0.201   0.625      0.17   <- here
#   0.240     0.050   0.533      0.07   (the synonym barely survives anymore)
#   0.280     0.000   0.500      0.00   (falseRec 0, but paraphrase recall is gone)
# At 0.19 the false rate stays at 0.17 across the three scales measured
# (real N 20/44/216) with global MRR 0.742/0.736/0.625, and the synonym stays
# alive, which is what sets hipercampo apart from BM25. Raising to 0.28 would
# give a flashy 0.00 in exchange for losing paraphrase recall: not worth it.
# It's a chosen, measured TRADE-OFF, not an optimum: no row wins on both columns.
ANSWER_MIN_SCORE = 0.19          # floor to ANSWER: if not even the best clears it, abstain
# INERT at scale: measured at N=500, z=2.0 and z=3.0 give identical rows across the
# whole sweep (the best anchor always clears mu+3sd with a tail of hundreds). It only
# bites with small memories, which is where it was set and where it's still needed.
# Don't touch without measuring it THERE.
RECALL_Z = 2.0                   # how many std devs above the noise to NOT abstain
# CORRECTION measured (scripts/calibrate.py --semantic, N=500). This used to say the
# semantic hook COMPRESSES activations against the noise, and that therefore the
# floor had to be LOWERED (to 0.05) and more z required. On this corpus it's the
# opposite: semantic separates BETTER than lexical, because it sinks the unrelated
# ones, not because it raises the hits.
#            positive p5/med/p95        unrelated p5/med/p95
#   lexical    0.112/0.327/0.518          0.099/0.160/0.239
#   semantic   0.164/0.298/0.462          0.078/0.124/0.180   <- unrelated sits lower
# At 0.05 the floor sat below ALL unrelated ones: falseRec 0.93. Calibrated to
# 0.17 outperforms lexical on BOTH columns at once (real N 20/44/219):
#   falseRec 0.07 / 0.07 / 0.10   ·   global MRR 0.833 / 0.814 / 0.751
# Each pair is measured in its own regime; they aren't interchangeable.
ANSWER_MIN_SCORE_SEM = 0.17
RECALL_Z_SEM = 2.5               # inert at N=500 just like RECALL_Z; kept for small N
NOISE_MIN_N = 5                  # min number of TAIL memories to apply the z-score
# MEASURED AND DECLARED LIMIT: length DILUTION. In a VSA bundle each component's
# signal is spread across everything superposed, so activation falls as 1/sqrt(T)
# with the memory's word count (measured: activation*sqrt(T) stays around
# ~0.95-1.21 while length varies 54x). Real consequence: a fact drowned in 60
# words of filler is UNRECOVERABLE (0 of 10 in scripts/calibrate.py).
#
# Fixing it by multiplying by (T/12)^exp was tried and DISCARDED after measuring.
# It looked like it fixed things (0/10 -> 10/10), but it was a mirage: the floor
# was left uncalibrated, so the system simply answered much more often
# (falseRec 0.17 -> 0.73). Matching the false rate, the correction LOSES on both
# benches at once:
#   exp   floor*  falseRec   MRR short    MRR long(rel=20)
#   0.00    0.19      0.17        0.625                0.800   <- uncorrected
#   0.25    0.39      0.17        0.188                0.000
#   0.50    0.39      0.17        0.175                0.300
# Reason: reinforcing by length also boosts long distractors and takes away the
# edge from the short, precise fact. The right answer to a long text isn't a
# scale factor, it's CHUNKING it into atomic facts (see ROADMAP). Don't retry
# without a bench that has both long AND short targets, and without matching
# falseRec before comparing.
# Switch ONLY for calibration (scripts/calibrate.py): with the gate open you can
# observe the ranking that WOULD have come out and sweep thresholds over the
# same signals, instead of re-running the memory once per threshold. Don't
# touch in production: turning it off removes abstention.
GATE_ENABLED = True
REINFORCE_MIN_SCORE = 0.10       # only reinforce what's clearly relevant (not a graze)
UPDATE_MIN_SIMILARITY = 0.60     # hc_update won't replace without a match this good
LINK_SIMILARITY = 0.58           # create an association between memories this similar
NAV_WRITE_NEIGHBORS = 4           # incremental knn per write (map, not evidence)
NAV_WRITE_MIN_MEMORIES = 6        # before this, don't close small creative wedges
CONSOLIDATE_SIMILARITY = 0.60    # fuse episodes this similar
DECAY_HALF_LIFE_DAYS = 14.0      # rate at which unreinforced strength fades
FORGET_STRENGTH_FLOOR = 0.15     # below this and unused -> pruning candidate
RETENTION_FLOOR = 0.40           # minimum retention value (4 axes) to NOT forget
UTILITY_CAP = 5                  # number of uses that already counts as "full utility"
DREAM_LOW = 0.55                 # sweet spot of the remote association (min)
DREAM_HIGH = 0.72                # sweet spot (max): neither redundant nor unrelated
DREAM_IDEAL = 0.63               # ideal similarity for a creative bridge
MIN_MUSE_GAIN = 0.05             # minimum gain from association for muse (indirect)
MUSE_DORMANT_FLOOR = 0.12        # a directly relevant dormant memory can resurface
MAX_TEXT_LEN = 20_000            # cap on a memory's length (defense)
# Cap on memories per context (0 = no limit). On reaching it, the one with the
# lowest retention (importance+confidence+utility) is pruned, never a protected
# one (importance>=0.8).
MAX_MEMORIES = int(os.environ.get("HIPERCAMPO_MAX_MEMORIES", "0") or "0")
# If on, secrets are MASKED before storing (not just flagged).
REDACT_SECRETS = os.environ.get("HIPERCAMPO_REDACT_SECRETS") == "1"
# AUTONOMOUS SLEEP: every how many writes the memory maintains itself
# (consolidates, forgets and proposes bridges) without anyone asking.
# 0 = disabled.
AUTOSLEEP_EVERY = int(os.environ.get("HIPERCAMPO_AUTOSLEEP_EVERY", "50") or "0")


def creative_fit(similarity: float) -> float:
    """Fit to the CREATIVE ZONE: max at DREAM_IDEAL and zero outside the band.
    Keeps the most dissimilar pair (an absurd connection) from winning just
    for being far away."""
    if similarity < DREAM_LOW or similarity > DREAM_HIGH:
        return 0.0
    if similarity <= DREAM_IDEAL:
        return (similarity - DREAM_LOW) / (DREAM_IDEAL - DREAM_LOW)
    return (DREAM_HIGH - similarity) / (DREAM_HIGH - DREAM_IDEAL)


def abstention_gate(direct, n_top: int, semantic: bool = False,
                    floor: float | None = None, zmin: float | None = None) -> tuple[bool, dict]:
    """
    Is there enough material to ANSWER, or is it time to stay quiet?

    `direct` are the DIRECT activations (no propagation), sorted from
    highest to lowest; `n_top` is how many will be returned. Returns
    (answer, diagnostic), and the diagnostic carries the raw signals (best,
    mu, sd, tail_n) so thresholds can be swept without re-running the memory
    — see `scripts/calibrate.py`.

    Deliberately a PURE function: the decision to abstain is the system's
    most delicate parameter and has to be measurable on its own, not just
    observed from outside.
    """
    if floor is None or zmin is None:
        _floor, _z = ((ANSWER_MIN_SCORE_SEM, RECALL_Z_SEM) if semantic
                      else (ANSWER_MIN_SCORE, RECALL_Z))
        floor = _floor if floor is None else floor
        zmin = _z if zmin is None else zmin

    best = float(direct[0]) if len(direct) else 0.0
    n_excl = min(max(n_top, 1), max(1, len(direct) - NOISE_MIN_N))
    tail = direct[n_excl:]
    diag: dict[str, Any] = {"best": best, "floor": floor, "zmin": zmin,
                            "tail_n": len(tail), "mu": None, "sd": None,
                            "z_threshold": None, "reason": None}

    if best < floor:                                  # nothing relevant at all
        diag["reason"] = "nothing relevant"
        return False, diag
    if len(tail) >= NOISE_MIN_N:
        mu, sd = float(tail.mean()), float(tail.std())
        diag.update(mu=mu, sd=sd, z_threshold=mu + zmin * sd)
        if best < mu + zmin * sd:                     # the best doesn't stand out from the noise
            diag["reason"] = "nothing stands out from the noise"
            return False, diag
    return True, diag
