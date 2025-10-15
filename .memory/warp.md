# Memory System

This directory contains the AI agent's memory files for the Indexed Python project. These files maintain context across sessions and guide development decisions.

## File Structure

### Global Context Files (Persistent)

These files contain long-term project information and should be updated as the project evolves:

- **`brief.md`** - Project overview, goals, current status, and features
- **`tech.md`** - Tech stack, coding standards, and development rules
- **`architecture.md`** - System architecture, design patterns, and data flows
- **`app_cli.md`** - CLI application specification and command details
- **`package_core.md`** - Core library architecture and implementation details
- **`migration_status.md`** - Migration history, current status, and roadmap

### Task-Specific Context Files (Temporary)

These files are created for specific tasks and cleared after completion:

- **`task_prd.md`** - Product requirements for current task
- **`task_plan.md`** - Technical implementation plan for current task
- **`design_specs.md`** - UI/UX design specifications (when needed)

## Memory Files Overview

### `brief.md` (5.3 KB)
**Project Brief & Overview**
- Product overview and value proposition
- Current implementation status (Phase 2, 87% complete)
- Monorepo structure details
- Core features (legacy + new architecture)
- Target users and use cases
- Development principles
- Current tasks and success criteria

### `tech.md` (10 KB)
**Tech Stack & Coding Rules**
- **CRITICAL**: uv package management rules (ALWAYS use `uv run`)
- Current tech stack (FAISS, sentence-transformers, Pydantic)
- Architecture patterns (Layered, Dependency Injection)
- Coding standards (Type safety, Error handling, Logging)
- Development workflow and required commands
- Configuration management
- Legacy code handling rules
- Testing requirements

### `architecture.md` (21.5 KB)
**System Architecture**
- High-level architecture diagrams
- Component responsibilities (CLI → Controllers → Services → Infrastructure)
- Data flow for indexing and search pipelines
- Configuration hierarchy
- Dependency injection pattern (ServiceFactory)
- Extension points for new features
- Storage architecture and file formats
- Legacy vs. New architecture migration strategy
- Performance considerations

### `app_cli.md` (12 KB)
**CLI Application Details (Legacy)**
- Previous CLI structure and commands
- Engine selection logic (legacy vs v2)
- MCP server integration
- Historical context

### `cli_final_design.md` (21 KB) ⭐ **CURRENT CLI SPEC**
**Final CLI Design v2.0**
- Complete command specification (6 commands total)
- Interactive-first design with automation support
- Search-first philosophy
- Rich library integration patterns
- Visual design guidelines (minimal colors)
- Logging strategy (clean by default)
- User workflows and examples
- Implementation priorities
- Success criteria

### `cli_rewrite_complete.md` (9 KB)
**Previous CLI Rewrite Session Summary**
- Documents Phase 2 Step 15 completion
- Historical record of previous implementation
- Architecture patterns used

### `package_core.md` (19 KB)
**Core Library Specification**
- Dual architecture (legacy + Phase 2)
- Configuration system (Pydantic models, ConfigService)
- Domain models (Document, Chunk, SearchResult)
- Service layer details (Storage, Embedding, Indexing, Search)
- Controller layer (IndexController, SearchController)
- Connector system (FileSystem, future: Git, Notion)
- Dependency injection pattern
- Implementation status (13 of 15 steps complete)
- Extension points
- Usage examples
- Testing strategy

### `migration_status.md` (14 KB)
**Migration History & Roadmap**
- Phase 1: Monorepo migration (✅ Complete)
- Phase 2: Controller/Service architecture (🔄 87% complete)
- Phase 3: Future enhancements (📋 Planned)
- Architecture comparison (legacy vs new)
- File organization and statistics
- Command status (current vs future)
- Data compatibility details
- Known issues and workarounds
- Next actions (Step 15: CLI integration)
- Timeline and success metrics

## Current Project Status (Quick Reference)

**Phase:** Phase 2 - Controller/Service Architecture  
**Branch:** `phase2-controller-service`  
**Completion:** 13 of 15 steps (87%)  
**Next Priority:** CLI Integration (Step 15)

**Recent Achievements:**
- ✅ Monorepo structure established
- ✅ Clean architecture implemented
- ✅ Configuration system complete
- ✅ All services and controllers done
- ✅ ServiceFactory (DI) complete

**Next Steps:**
- ⏳ CLI integration with v2 commands
- ⏳ Tests (optional, incremental)
- 📋 Enhanced CLI with Rich UI
- 📋 Additional providers/connectors

## Usage Guidelines

### When to Read Memory Files

**At Session Start:**
1. Read `brief.md` for project overview
2. Read `migration_status.md` for current state
3. Read `tech.md` for coding rules
4. Read relevant component files as needed

**When Working on CLI:**
- Read `app_cli.md` for CLI details
- Read `migration_status.md` for next steps

**When Working on Core:**
- Read `package_core.md` for implementation details
- Read `architecture.md` for design patterns

**When Starting New Task:**
- Read all relevant memory files
- Create `task_prd.md` and `task_plan.md`

### When to Update Memory Files

**Global Context Files:**
- Update when project structure changes
- Update when major features are added
- Update when tech stack changes
- Update when architecture evolves
- Update when phase milestones are reached

**Task-Specific Files:**
- Create at task start
- Update during task execution
- Clear after task completion

### Memory File Protocol

According to the MANDATORY CODING AGENT PROTOCOL:

**Session Start:**
1. ✅ READ all memory files
2. ✅ VERIFY context is current and complete
3. ✅ UPDATE outdated information immediately
4. ✅ If memory files missing, CREATE them first
5. ✅ ASSESS task complexity and determine mode

**Task Execution:**
1. ✅ CREATE `task_prd.md` for new tasks
2. ✅ CREATE `task_plan.md` for implementation
3. ✅ UPDATE memory files as work progresses
4. ✅ CLEAR task files when complete

## Initialization History

**Initialized:** October 5, 2024  
**Created From:**
- `ARCHITECTURE.md` - System architecture
- `DEVELOPMENT.md` - Development workflow
- `MIGRATION.md` - Phase 1 migration details
- `PHASE2_IMPLEMENTATION_PLAN.md` - Phase 2 specifications
- `PHASE2_STATUS.md` - Current implementation status
- `.prd/prd.md` - Product requirements
- `.prd/tech.md` - Technology stack
- `.prd/architecture.md` - Architecture details
- `.prd/apps/cli.md` - CLI specifications
- `.prd/packages/core.md` - Core library specs

### Memory Files Created

1. **`brief.md`** - Synthesized from PRD and project status
2. **`tech.md`** - Tech stack, coding rules, development workflow
3. **`architecture.md`** - Complete system architecture
4. **`app_cli.md`** - CLI application details from PRD
5. **`package_core.md`** - Core library specifications
6. **`migration_status.md`** - Migration history and roadmap
7. **`README.md`** - This file

**Total:** 7 comprehensive memory files covering all aspects of the project

## File Statistics

| File | Size | Purpose |
|------|------|---------|
| `brief.md` | 5.3 KB | Project overview |
| `tech.md` | 10 KB | Tech stack & rules |
| `architecture.md` | 21.5 KB | System architecture |
| `app_cli.md` | 12 KB | CLI application |
| `package_core.md` | 19 KB | Core library |
| `migration_status.md` | 14 KB | Migration & status |
| `README.md` | This file | Memory system guide |

**Total Memory:** ~82 KB of comprehensive project documentation

## Maintenance

Keep these files synchronized with:
- Project documentation in root directory
- Actual codebase structure
- Current development phase
- Active technical decisions
- Migration progress

**Update Frequency:**
- After major feature completions
- When architecture changes
- When new phases begin
- When development priorities shift

## Quick Navigation

**For Architecture Questions:**
- See `architecture.md` for overall design
- See `package_core.md` for core implementation
- See `app_cli.md` for CLI details

**For Development Guidelines:**
- See `tech.md` for coding standards
- See `brief.md` for project goals
- See `migration_status.md` for current work

**For Migration/Roadmap:**
- See `migration_status.md` for complete timeline
- See `brief.md` for current status
- See `package_core.md` for Phase 2 details

## Success Indicators

✅ **Complete Context:** All project aspects documented  
✅ **Current Status:** Phase 2 at 87% completion clearly tracked  
✅ **Clear Next Steps:** CLI integration (Step 15) identified  
✅ **Architecture Clarity:** Both legacy and new architectures explained  
✅ **Development Rules:** Comprehensive coding guidelines documented  
✅ **Migration Path:** Clear roadmap from Phase 1 → 2 → 3  

**The memory system is comprehensive, current, and ready to guide development! 🚀**

---

**Last Updated:** October 5, 2024  
**Status:** ✅ Complete and validated against all project documentation
