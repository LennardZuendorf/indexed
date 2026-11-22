---
type: tech
updated: 2026-11-22
applies: [scripts/check_imports.py, "src/indexed/**"]
---

# Import-Graph CI

`scripts/check_imports.py` (also run in CI, alongside `scripts/check_sizes.py`)
AST-walks `src/indexed` and fails on forbidden edges — the four rules above,
expanded:

| From | Must NOT import |
|------|-----------------|
| `core` | `connectors`, `cli`, `mcp` |
| `connectors` | `core`, `cli`, `mcp` |
| `config`, `parsing`, `utils`, `protocols` | `core`, `connectors`, `cli`, `mcp` |

`cli`/`mcp` sit at the top of the stack and may import any subpackage — they have
no forbidden edge of their own. Run `python scripts/check_imports.py --self-test`
to verify a synthetic forbidden edge is still caught.
