"""
SUPPORT — the cross-cutting bits: where the memory lives, what gets logged,
and what it costs.

    config     DB path, pause ('do not record'), and persisted budget
    audit      decision log (what it did and why), to stderr and to a file
    budget     token budget: keeping the memory from eating the window
    safety     secret and memory-injection warnings
    procs      which MCP servers are alive (for `servers` and `restart`)

Depends only on itself. Used by every layer above.
"""
