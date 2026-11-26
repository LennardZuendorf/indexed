---
type: concept
updated: 2026-11-23
---

# Product overview

Indexed gives developers and agents searchable project context across code,
documentation, issues and other development evidence. Indexing and ranking run
locally. Connectors fetch configured sources, and model preparation downloads the
files needed for local inference.

A developer can ask why code exists, find the issue or wiki page that explains
it, and follow the result to the relevant symbol or change. Developers and
agents in the same project search the same repository-selected collections.
Multiple projects can use the same index data.

**Shipped today:** local files, Jira, Confluence, Outline and GitHub through CLI
and MCP, with Git provenance, local watching, editor navigation and a Claude Code
installer.

**Readiness target:** shared global collections with a repo definition, measured
merged search over GitHub issues, a local Markdown wiki and code, searchable Git
history and development sources, code graph traversal, a full language server for
supported languages, and plugin setup across the target agent clients. Clear
documentation and product copy make these workflows usable from a clean install.

**Status:** [Alpha v0.0.11](https://github.com/LennardZuendorf/indexed/releases/tag/v0.0.11).

**Privacy:** keep indexing, embedding and ranking local. Fetch configured remote
sources and requested model files.

- [Readiness milestones](readiness/README.md): the six capabilities the product is measured against.
- [Technical contracts](../tech/readiness-contracts.md): the contracts that constrain their designs.
