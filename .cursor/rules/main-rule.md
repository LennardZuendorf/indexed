# 📝 MEMORY MANAGEMENT PROTOCOLS

**🚨 CRITICAL: These memory protocols MUST be followed WITHOUT EXCEPTION.**

## MEMORY FILE STRUCTURE

### Global Context Files (Persistent)
Files that maintain system-wide context and must persist across sessions:

1. **`tech.md`** - Tech Stack and Style Rules
   - Tech stack specifications
   - Coding standards and conventions
   - Style guidelines and patterns
   - UPDATE when stack changes or new conventions are established

2. **`brief.md`** - Project Brief and Context
   - Product goals and objectives
   - Project scope and constraints
   - Overall system purpose
   - UPDATE when product goals or scope changes

3. **`architecture.md`** - System Architecture
   - System components and relationships
   - Design patterns and decisions
   - Interface contracts and APIs
   - UPDATE when architecture evolves

### Task-Specific Files (Clear after completion)
Files that track current task progress and are cleared upon completion:

1. **`task_prd.md`** - Current Task Requirements
   - Problem statement
   - User stories and requirements
   - Technical constraints
   - Success criteria
   - CLEAR after task completion

2. **`task_plan.md`** - Implementation Plan
   - Technical approach
   - Component specifications
   - Implementation steps
   - CLEAR after task completion

3. **`task_subtasks.md`** - Task Progress
   - Subtask breakdown
   - Progress tracking
   - Validation results
   - CLEAR after task completion

## MEMORY PROTOCOLS

### Session Start Protocol
BEFORE ANY WORK:
1. ✅ READ all persistent memory files
2. ✅ VERIFY content is current and complete
3. ✅ UPDATE outdated information
4. ✅ CREATE missing files
5. 🚫 NEVER proceed without complete memory context

### File Update Protocol
RULES FOR UPDATING FILES:

**Persistent Files:**
- ✅ UPDATE when system context changes
- ✅ MAINTAIN historical context
- ✅ DOCUMENT update rationale
- 🚫 NEVER delete without replacement
- 🚫 NEVER make partial updates

**Task Files:**
- ✅ UPDATE in real-time during task
- ✅ TRACK all progress incrementally
- ✅ CLEAR after task completion
- 🚫 NEVER mix multiple tasks
- 🚫 NEVER leave stale content

### Memory Validation Protocol
REGULAR VALIDATION REQUIRED:

1. Content Validation
   - ✅ Files exist in correct location
   - ✅ Content is complete and current
   - ✅ Format follows templates
   - ✅ No conflicting information

2. Cross-Reference Validation
   - ✅ Files are internally consistent
   - ✅ Dependencies are tracked
   - ✅ Changes are propagated
   - ✅ No orphaned references

## FILE TEMPLATES

### tech.md Template
```markdown
# Technology Stack

## Frontend
- Framework: [Name & Version]
- UI Components: [List]
- State Management: [Solution]

## Backend
- Language: [Name & Version]
- Framework: [Name & Version]
- Database: [Type & Version]

## Development
- Build Tools: [List]
- Testing Framework: [Name]
- Code Quality: [Tools]

## Conventions
[Language/Framework-specific conventions]

## Style Guide
[Project style guidelines]
```

### brief.md Template
```markdown
# Project Brief

## Overview
[Project description and goals]

## Objectives
- [Primary objectives]
- [Success metrics]

## Scope
[Project boundaries and constraints]

## Stakeholders
[Key stakeholders and roles]
```

### architecture.md Template
```markdown
# System Architecture

## Overview
[High-level architecture description]

## Components
[Component breakdown and relationships]

## Interfaces
[API contracts and specifications]

## Data Flow
[System data flow patterns]

## Design Decisions
[Key architectural decisions and rationale]
```

### task_prd.md Template
```markdown
# Task Requirements

## Problem Statement
[Clear problem definition]

## Requirements
- Functional: [List]
- Non-functional: [List]

## Constraints
[Technical and business constraints]

## Success Criteria
[Measurable success metrics]
```

### task_plan.md Template
```markdown
# Implementation Plan

## Approach
[Technical approach description]

## Components
[Affected components and changes]

## Steps
1. [Implementation step 1]
2. [Implementation step 2]
   ...

## Dependencies
[Required dependencies and prerequisites]
```

### task_subtasks.md Template
```markdown
# Task Progress

## Subtasks
- [ ] [Subtask 1]
  - Status: [Not Started/In Progress/Complete]
  - Validation: [Not Validated/Passed/Failed]
- [ ] [Subtask 2]
  ...

## Notes
[Implementation notes and observations]

## Blockers
[Current blockers or issues]
```

## MANDATORY SUCCESS CRITERIA

- [ ] All memory files exist and are correctly located
- [ ] File content follows specified templates
- [ ] Persistent files maintain system context
- [ ] Task files track current progress
- [ ] Updates follow prescribed protocols
- [ ] Regular validation is performed
- [ ] No stale or conflicting information exists

**REMEMBER: Memory integrity is CRITICAL. These protocols are NOT optional. Every violation creates system confusion and implementation risk.**