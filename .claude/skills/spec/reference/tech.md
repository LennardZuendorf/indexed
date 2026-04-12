# Writing Tech Specs

Tech specs answer **how**. Architecture, code patterns, data flow, file paths, code examples — all welcome. UX opinions are not — reference the product spec instead.

There are three places tech content goes. Pick the right one.

---

## 1. Root: `tech.md`

The architecture summary. **Stay high-level.** No feature-level detail.

Sections:
- **Design philosophy** — 3-7 technical principles that constrain decisions
- **Architecture overview** — directory tree with annotations (NEW / inherited / extended)
- **Tech stack** — inherited and added, with versions
- **State / data contracts** — file formats, protocols, invariants that span features
- **Build vs Inherit** — table of LOC by source so you know what you're actually writing
- **Basic implementation** — small support pieces that don't warrant their own feature (installer scripts, conventions)
- **Build sequence** — table mapping components to features and milestones
- **Risks & mitigations** — technical risks at the project level
- **Features index** — table linking to `features/<name>/tech.md`

If you're describing how one feature is implemented, you're in the wrong file. Move to `features/<name>/tech.md`.

---

## 2. Feature: `features/<name>/tech.md`

Where feature-level architecture lives. **Short-lived** — created during DESIGN, merged into root + archived after COMPOUND.

Sections:
- **Files** — what gets created or modified, with paths
- **Contract / API** — interfaces, types, function signatures
- **Implementation detail** — algorithms, data flow, code examples
- **Performance budget** — if applicable
- **Open questions** — feature-scoped technical questions

Mark cross-cutting sections with `<!-- merge -->` ... `<!-- /merge -->` so the COMPOUND merge tooling can promote them into root `tech.md`. Feature-specific detail is not marked and stays in archive.

Frontmatter:
```yaml
---
type: feature-tech
feature: <name>
sibling: product.md
parent: ../../tech.md
updated: YYYY-MM-DD
---
```

---

## 3. Branch: `tech-{topic}.md`

**For cross-cutting concerns only.** Infrastructure. Observability. CI/CD. Deployment. Database conventions. Things that don't belong to one feature.

Create when:
- The technical area applies to every feature
- Multiple features reference this area independently
- Implementation guidance for this area prevents mistakes across the project

Frontmatter:
```yaml
---
type: branch
parent: tech.md
scope: <topic>
covers: <comma-separated list>
updated: YYYY-MM-DD
---
```

If the topic is really about one feature, it's not a branch doc — it's a feature.

---

## Style Rules

**Do:**
- Include real code examples with file path comments
- Show interface/type definitions for key data structures
- Use tables for API surfaces, channels, configuration
- Reference actual codebase paths
- Describe data flow with concrete steps
- List what already exists and should NOT be rebuilt
- State decisions with trade-off rationale

**Don't:**
- Describe user experience or interaction design
- Use words like "intuitive", "clean", "user-friendly"
- Make UX decisions — reference the product spec instead
- Write aspirational architecture — describe what you're actually building

**Example — Describing an Implementation:**
```markdown
## File Watcher

Agent writes to disk → main process detects via `fs.watch` → renderer reloads.

Conflict prevention:
- Auto-save triggers before every agent query
- Own-write tracking: main process records timestamps of writes it initiated
- Writes within 500ms of own-write are ignored

```typescript
// apps/electron/src/main/services/files.ts
const ownWrites = new Map<string, number>();

function onFileChange(filePath: string) {
  const ownWrite = ownWrites.get(filePath);
  if (ownWrite && Date.now() - ownWrite < 500) return;
  notifyRenderer('file:changed', { path: filePath });
}
```
```

Real path. Real code. Concrete algorithm. No UX opinions.

---

## Cross-References

Always link to your product counterpart:
```markdown
**Requirements:** [product.md](product.md)
**Requirements:** [../../product.md](../../product.md)  # from feature to root
```

---

## When to Update vs Create

- **Update** an existing doc when adding detail to an existing area
- **Create a feature** when scoping new architecture for a buildable unit of work
- **Create a branch doc** only when a genuinely cross-cutting technical concern emerges
- **Never** create a branch doc that's really about one feature — that's a feature
- **Never** put feature-level implementation detail in `tech.md` — keep it high-level

---

## Templates

- **Root entrypoint:** [templates/tech.md](templates/tech.md)
- **Feature spec:** [templates/feature-tech.md](templates/feature-tech.md)
- **Cross-cutting branch:** [templates/tech-xxx.md](templates/tech-xxx.md)
