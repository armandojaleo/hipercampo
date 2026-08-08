# Attribution and provenance

This project is explicit about what is original and what owes credit to third
parties. House rule: **if we use someone else's work—especially copyrighted
work—we say so.**

## Code

**All code under `hipercampo/` is original**, written for this project by Armando
Jaleo with assistance from Anthropic's Claude. No copyrighted code has been copied
from other projects. The hypervector algebra (`bind` = XOR, `bundle` = majority
vote, `permute` = rotation, Hamming distance) consists of standard public-domain
mathematical operations, not someone else's implementation.

## Software dependencies and their licences

These are installed separately through `pip`; **their code is not included** in
this repository.

| Dependency | Use | Licence |
|---|---|---|
| [NumPy](https://numpy.org) | Hypervector operations | BSD-3-Clause |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MCP server (`FastMCP`) | MIT |
| Python (stdlib: `sqlite3`, `hashlib`, `re`) | Persistence and utilities | PSF |

Each dependency retains its own licence and copyright.

### OPTIONAL semantic-hook dependency (not installed by default)

Only when semantics are enabled with `pip install hipercampo[semantic]`:

| Dependency / resource | Use | Licence |
|---|---|---|
| [sentence-transformers](https://github.com/UKPLab/sentence-transformers) | Generate dense embeddings | Apache-2.0 |
| `paraphrase-multilingual-MiniLM-L12-v2` model (default) | Multilingual embeddings | Apache-2.0 (model authors) |

The SimHash bridge (`semantic.embedding_to_hv`) that converts those embeddings
into hypervectors is **our original code**. Users download the model themselves,
and it remains governed by its own licence. You can replace it with any other
model through `make_hook`.

## Ideas and academic work that inspired us

hipercampo **does not implement** these works; it draws inspiration from their
ideas and cites them accordingly. The concepts belong to their authors:

- **Pentti Kanerva** — *Sparse Distributed Memory*.
- **Tony A. Plate** — *Holographic Reduced Representations* (HRR / binding).
- **Torchhd** — Heddes et al., *JMLR* 2023: a reference HD/VSA library. We cite it
  as prior art; **we do not use its code** and implement our own VSA.
- Recent work on LLM memory (2024–2026): **Titans**, **MIRAS**, **HippoRAG**,
  **MemGPT / Letta**, **Mem0**, **Graphiti**, and **MnemoCore** (HDC/VSA for AI
  memory), as well as the relationship *attention ≈ SDM* (Bricken & Pehlevan,
  2021). They helped locate the gap worth exploring; none contributed code to
  this repository. hipercampo does not claim to have invented HDC or agent memory.
  It claims a concrete *combination*: VSA + surprise + consolidation + forgetting,
  exposed through MCP.

## The optional semantic hook

`encoder.set_semantic_hook()` lets users connect an external semantic encoder,
such as an embedding model. **hipercampo includes no model.** If you connect one,
that model brings its own licence and terms, which you accept; declare it in your
deployment.

## How to cite hipercampo

> Jaleo, A. (2026). *hipercampo: hypervector-based associative memory for LLMs*.
> https://github.com/armandojaleo/hipercampo
