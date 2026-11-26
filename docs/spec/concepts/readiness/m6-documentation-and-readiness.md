---
type: concept
updated: 2026-11-23
---

# Documentation and Readiness (M6)

[GitHub milestone 16](https://github.com/LennardZuendorf/indexed/milestone/16) · [Parent issue #343](https://github.com/LennardZuendorf/indexed/issues/343) · [Readiness](README.md)

A developer can understand the product from the README or site and complete the advertised project-evidence workflow using the published package.

| Requirement | Observable behavior |
| --- | --- |
| Clear positioning | Lead with the task Indexed helps complete. Explain collections, repo selection and evidence through concrete examples. README, site and CLI help use consistent names and commands. |
| Versioned claims | Published docs identify the tested package, Python range, client/language support, source limitations, and what model files must be prepared before offline use. |
| Complete onboarding | The docs cover installation, scoping, indexing sources, searching, graph exploration and citations. Migration and troubleshooting guides cover observable failures and recovery. |
| Demonstrated value | Repeat representative developer-agent tasks with and without Indexed. Publish the artifact, fixture or revision, scoring criteria, observed citation quality, failures and effort. |

**Acceptance.** A new user follows published examples in a clean environment from the wheel to the end-to-end workflow. Independently replay the before/after agent tasks for implementation, rationale, exact-identifier lookup, changed-source evidence and an unanswerable request. Verify all commands, links and support claims against the selected release evidence. Report first-run model download separately from warmed setup and search timing.

The readiness copy is now bounded in the repository: [README](../../../../README.md) states Python 3.11–3.14, and [pyproject](../../../../pyproject.toml) carries the same range. What remains is the published v0.0.11 site ([#336](https://github.com/LennardZuendorf/indexed/issues/336), [#218](https://github.com/LennardZuendorf/indexed/issues/218)).

Issues: [#218 public docs and product copy](https://github.com/LennardZuendorf/indexed/issues/218) · [#174 CLI onboarding](https://github.com/LennardZuendorf/indexed/issues/174) · [#220 installed workflow and task trial](https://github.com/LennardZuendorf/indexed/issues/220) · [#336 Python support](https://github.com/LennardZuendorf/indexed/issues/336).
