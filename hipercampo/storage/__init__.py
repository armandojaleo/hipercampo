"""
STORAGE — persistence. A single, portable SQLite file.

    store      memories, packed hypervectors, and the association graph
    backup     consistent backup and restore (SQLite's backup API)

Depends on `core` (to compare hypervectors) and on `support` (paths). Knows
nothing about the memory cycle: what to store or forget isn't decided here,
only how.
"""
