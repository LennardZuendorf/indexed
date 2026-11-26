---
type: concept
updated: 2026-11-23
---

# Code Graph and Language Server (M4)

[GitHub milestone 14](https://github.com/LennardZuendorf/indexed/milestone/14) · [Parent issue #341](https://github.com/LennardZuendorf/indexed/issues/341) · [Readiness](README.md)

A developer can move from search evidence to code structure, language-aware relationships and the development records that explain the result.

| Requirement | Observable behavior |
| --- | --- |
| Search to tree | Open a hit at its source location and inspect its enclosing scope and child syntax or symbols. Carry repository, revision and location across CLI, MCP and the editor. |
| Typed graph | Follow available definitions, references, imports and calls. Each edge identifies its type, source and whether it came from syntax or semantic resolution. Traversal reports its limits and any unavailable continuation. |
| Linked evidence | Follow attributable links among code, commits, PRs and issues. Edits, renames, deletions and revision mismatches have visible outcomes. |
| Editor workflow | Publish a language and capability matrix covering symbols, hover, definitions, references, implementations, type and call navigation, diagnostics, completion, signatures, rename, formatting and code actions. Validate the required editor workflows in the initial supported languages. Record each capability as verified, partial or unsupported. Document and test delegated capabilities, and retain unverified items as readiness gaps. |

**Acceptance.** Start with the search hit in an editor, find the enclosing function, follow a semantically resolved caller and cite the associated commit or issue. Repeat traversal through CLI and MCP. Include same-named symbols in different scopes, a cycle, cancellation, a stale range, unsaved editor changes, Unicode positions and an unsupported edge. Test advertised editor capabilities, including editing operations where declared, against the same language support matrix.

The feature design chooses the initial supported languages and the semantic providers. The milestone owns a tested capability matrix and distinguishes semantic resolution from approximate search navigation.

Issues: [#241 LSP capabilities](https://github.com/LennardZuendorf/indexed/issues/241) · [#148 linked evidence](https://github.com/LennardZuendorf/indexed/issues/148). [#353 code graph traversal](https://github.com/LennardZuendorf/indexed/issues/353) owns semantic code relationships and search-to-tree exploration.
