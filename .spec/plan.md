---
type: plan
scope: roadmap
updated: 2026-02-16
---

# Development Plan: indexed

Phased roadmap for indexed development from v0.1.0 (current) to v1.0.0.

**For feature specs, see [product.md](product.md).**
**For technical implementation, see [tech.md](tech.md).**

---

## Current Status: v0.1.0 Alpha

**Released:** 2026-02-16
**Status:** ✅ Complete

---

## Phase 1: Foundation (v0.1.0) ✅ Complete

**Goal:** Core functionality working end-to-end

**Delivered:**
- Core indexing pipeline (read → convert → chunk → embed → index → persist)
- FAISS vector search with L2 distance
- Jira Cloud & Server connectors
- Confluence Cloud & Server connectors
- File system connector
- MCP server with stdio/HTTP/SSE transports
- CLI with all core commands (create, search, update, inspect, remove)
- Configuration system (TOML + env vars + CLI args)
- Test coverage >85%
- Docker support
- Monorepo build with `una`

**What works:**
- Privacy-first local indexing and search
- AI agent integration via MCP
- Multi-source document indexing
- Semantic similarity search
- Beautiful CLI with Rich output

---

## Phase 2: Enhancement (v0.2.0) 📋 Planned Q2 2026

**Goal:** More sources, better search, improved UX

### New Connectors

- [ ] GitHub repositories (code + issues + PRs)
- [ ] Google Drive (Docs, Sheets, Slides)
- [ ] Notion (pages + databases)
- [ ] Slack (messages + threads)
- [ ] Email (IMAP)

### Search Improvements

- [ ] Filters (date range, source type, metadata fields)
- [ ] Boolean operators (AND, OR, NOT)
- [ ] Phrase search (exact matches)
- [ ] Fuzzy matching
- [ ] Query suggestions/autocomplete

### UX Enhancements

- [ ] Interactive TUI mode (full-screen interface)
- [ ] Better progress bars for long operations
- [ ] Improved error messages with suggestions
- [ ] Collection templates (presets for common setups)
- [ ] Interactive setup wizard

### Performance

- [ ] Parallel indexing (multi-threaded embedding)
- [ ] Query result caching
- [ ] Index compression
- [ ] Incremental update optimization

### Developer Experience

- [ ] Python API documentation (auto-generated)
- [ ] Video tutorials
- [ ] Example projects
- [ ] Connector development guide

---

## Phase 3: Scale (v0.3.0) 📋 Planned Q3 2026

**Goal:** Production readiness, multi-user support, enterprise features

### Multi-User Support

- [ ] Server mode (persistent HTTP server)
- [ ] User authentication
- [ ] Per-collection access control
- [ ] Role-based permissions (admin, editor, viewer)

### Enterprise Features

- [ ] Audit logging (who searched what, when)
- [ ] Backup/restore (automated or manual)
- [ ] Collection replication
- [ ] High availability setup guide
- [ ] Monitoring & metrics (Prometheus/Grafana)

### Advanced Indexing

- [ ] Image OCR support (extract text from images)
- [ ] Audio transcription (index podcasts, meetings)
- [ ] Video subtitle extraction
- [ ] Code-aware chunking (respect function boundaries)
- [ ] Table extraction from documents

### API Expansion

- [ ] REST API server mode
- [ ] GraphQL endpoint
- [ ] Webhook support (notify on collection updates)
- [ ] Batch operations API

### Deployment

- [ ] Kubernetes Helm charts
- [ ] Official Docker Hub images
- [ ] Cloud provider templates (AWS, GCP, Azure)
- [ ] Terraform modules

---

## Phase 4: Ecosystem (v1.0.0) 🔮 Planned Q4 2026

**Goal:** Extensibility, community growth, long-term sustainability

### Connector Marketplace

- [ ] Third-party connector registry
- [ ] Plugin system architecture
- [ ] Connector SDK with examples
- [ ] Community connector showcase

### Embedding Flexibility

- [ ] Multi-model support (OpenAI, Cohere, custom)
- [ ] Per-collection model selection
- [ ] Fine-tuned domain models
- [ ] Model comparison tool

### Advanced AI Features

- [ ] Query reformulation (understand intent)
- [ ] Result summarization (LLM-powered)
- [ ] Related document suggestions
- [ ] Knowledge graph extraction
- [ ] Semantic clustering

### Community & Ecosystem

- [ ] Comprehensive tutorial series
- [ ] Video guides and demos
- [ ] Community showcase (user projects)
- [ ] Conference talks
- [ ] Blog posts and case studies

### Sustainability

- [ ] Clear licensing decision
- [ ] Contribution guidelines
- [ ] Code of conduct
- [ ] Governance model
- [ ] Potential monetization (enterprise support, hosted option)

---

## Versioning Strategy

**Semantic Versioning:** `MAJOR.MINOR.PATCH`

- **MAJOR (0 → 1):** Stable API, production-ready
- **MINOR (0.1 → 0.2):** New features, backward compatible
- **PATCH (0.1.0 → 0.1.1):** Bug fixes, no new features

**Alpha (current):** Breaking changes allowed, active development
**Beta (v0.5+):** API stabilizing, fewer breaking changes
**Stable (v1.0):** Semantic versioning guarantees

---

## Release Schedule

| Version | Target Date | Status |
|---------|-------------|--------|
| v0.1.0 | 2026-02-16 | ✅ Released |
| v0.2.0 | Q2 2026 | 📋 Planned |
| v0.3.0 | Q3 2026 | 📋 Planned |
| v1.0.0 | Q4 2026 | 🔮 Envisioned |

**Note:** Dates are targets, not commitments. Quality over schedule.

---

## Priority Matrix

### Must Have (P0)

- All Phase 1 features (complete)
- Phase 2 search improvements
- Phase 2 new connectors (at least 2)

### Should Have (P1)

- Phase 2 UX enhancements
- Phase 2 performance optimizations
- Phase 3 multi-user support

### Nice to Have (P2)

- Phase 3 enterprise features
- Phase 4 advanced AI features
- Phase 4 ecosystem

---

## Success Criteria

### v0.2.0 (Phase 2)

- [ ] At least 2 new connectors implemented
- [ ] Search filters functional
- [ ] TUI mode working
- [ ] >85% test coverage maintained
- [ ] No performance regression

### v0.3.0 (Phase 3)

- [ ] Multi-user server mode operational
- [ ] Access control implemented
- [ ] Production deployment guide
- [ ] At least 1 large-scale deployment (>1M docs)

### v1.0.0 (Phase 4)

- [ ] Stable API (no breaking changes)
- [ ] Comprehensive documentation
- [ ] Active community (GitHub stars, contributors)
- [ ] Production deployments at scale
- [ ] Clear governance and sustainability model

---

## Dependencies & Blockers

### Phase 2

**Dependencies:**
- None (can start immediately)

**Potential Blockers:**
- Connector API rate limits (may need throttling)
- Large document parsing performance (may need streaming)

### Phase 3

**Dependencies:**
- Phase 2 performance work (needed for multi-user)

**Potential Blockers:**
- Database choice for multi-user (PostgreSQL? SQLite?)
- Authentication strategy (OAuth? JWT? API keys?)

### Phase 4

**Dependencies:**
- Phase 3 API stability
- Community adoption and feedback

**Potential Blockers:**
- Embedding model licensing (commercial use restrictions?)
- Plugin security model (sandboxing?)

---

## Decision Log

### 2026-02-16: Initial Phases Defined

**Decision:** Four-phase roadmap with quarterly targets
**Rationale:** Provides clear milestones while maintaining flexibility
**Alternatives Considered:** Agile without roadmap (rejected: need direction)

### 2026-02-16: Alpha Status

**Decision:** Mark v0.1.0 as alpha, breaking changes allowed
**Rationale:** Need flexibility to iterate on API based on feedback
**Alternatives Considered:** Call it beta (rejected: too early)

---

## Open Planning Questions

1. **Phase 2 Connector Priority** — Which 2 connectors should be first? GitHub most requested? Google Drive most useful?

2. **Multi-User Architecture** — Database-backed or keep JSON? PostgreSQL + pgvector? SQLite for simplicity?

3. **Licensing** — MIT for maximum adoption? Apache 2.0 for patent protection? Commercial dual-license?

4. **Community Building** — When to start active marketing? Wait until beta? Conference talks in Q3?

5. **Sustainability** — Enterprise support model? Hosted option? Sponsorware? Keep fully open?
