---
type: tech
updated: 2026-11-22
applies: "src/indexed/**"
---

# No Dual Code Paths

If a value is accessible via dependency injection (lifespan state, constructor arg)
**and** via a global/singleton, pick one path. Never maintain both with fallback logic.
