"""
CYCLE — the memory proper: what's stored, what's retrieved, what's forgotten.

    memory     the four threads: surprise, propagation, consolidation, forgetting
    roles      compositional fact memory (VSA role-filler) and query by role
    policy     what's needed this turn of the conversation (recall, inspire, stay quiet)
    identity   the AGENT's own memory: rules, lessons and decisions that survive

This is the TOP layer over the core: it uses `core`, `storage` and
`support`, and knows nothing about transport. That's why `import
hipercampo` doesn't pull in `mcp` (see `tests/test_core_embebible.py`,
which fails if someone breaks that boundary).
"""
