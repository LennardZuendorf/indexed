---
type: concept
updated: 2026-11-23
---

# Agent Plugin Installation (M5)

[GitHub milestone 15](https://github.com/LennardZuendorf/indexed/milestone/15) · [Parent issue #222](https://github.com/LennardZuendorf/indexed/issues/222) · [Readiness](README.md)

A developer can add Indexed to an agent through a versioned installer and see what the installed integration can do.

| Requirement | Observable behavior |
| --- | --- |
| Six clients | Claude Code, Codex, OpenCode, Droid, Hermes Agent and OpenClaw each have a tested adapter, a supported-version record and matching setup instructions. |
| MCP, skills and hooks | Each adapter registers MCP, makes the Indexed skill discoverable and executes a host hook or an equivalent tested lifecycle adapter. Each client can search the selected repository and explore a result. |
| Safe lifecycle | A clean install, repeat install, upgrade and uninstall preserve unrelated user configuration. A partial failure has a documented retry or recovery outcome. |
| Coverage | Record native support, equivalent adapter behavior and remaining gaps per client. A missing capability keeps that matrix entry open. |

**Acceptance.** In a clean profile for each client, install, discover MCP and the skill, observe hook execution, search scoped evidence, and follow a result. Repeat installation, upgrade and remove the adapter with existing unrelated config present. Retain the host, host version, artifact and results for each action.

Agent lifecycle hooks are owned here. Git-triggered refresh remains under [#67](https://github.com/LennardZuendorf/indexed/issues/67).

Issues: [#222 agent plugins](https://github.com/LennardZuendorf/indexed/issues/222) · [#351 Droid](https://github.com/LennardZuendorf/indexed/issues/351) · [#352 Hermes Agent](https://github.com/LennardZuendorf/indexed/issues/352) · [#354 OpenClaw](https://github.com/LennardZuendorf/indexed/issues/354) · [#348 shared lifecycle contract](https://github.com/LennardZuendorf/indexed/issues/348).

- **Delivered on `main` since v0.0.11.** Installer lifecycles with host hooks for Claude Code, Codex and OpenCode (#364, #365, #368), one module per host.
