# Examples

Runnable use cases showing what hipercampo does. Each script uses a temporary DB and
cleans up after itself. Run from the repo root:

```bash
python examples/01_personal_assistant.py    # memory across sessions: remember, update, recall
python examples/02_project_knowledge.py     # structured facts + role queries (who/what/where)
python examples/03_creative_brainstorm.py   # creative recall (hc_muse): dormant memories resurface
python examples/04_the_long_night.py        # the full cycle: surprise, sleep, forgetting, dream, eureka
```

| # | Use case | Highlights |
|---|----------|-----------|
| 01 | **Personal assistant** | Remembers who you are, updates facts that change (Figma→Penpot), keeps important over trivial. `hc_remember` / `hc_update` / `hc_recall`. |
| 02 | **Project knowledge base** | Stores subject-predicate-object facts and answers *who/what/where* by role (VSA unbinding). `hc_remember_fact` / `hc_ask_role`. |
| 03 | **Creative brainstorming** | Forgetting makes memories *dormant* (not deleted); `hc_muse` resurfaces distant ones and ties ideas together, telling you the *bridge* that connected them. |
| 04 | **The long night** | The full cycle end to end over simulated weeks: surprise-driven writes, sleep, time-based pruning, dream's proposed bridges, and a `hc_muse` eureka moment. |

These are the same capabilities Claude gains as MCP tools — see the main
[README](../README.md) / [README.es](../docs/README.es.md).
