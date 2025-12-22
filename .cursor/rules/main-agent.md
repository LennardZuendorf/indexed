# 🤖 AGENT OPERATION PROTOCOLS

**🚨 CRITICAL: These mode protocols MUST be followed WITHOUT EXCEPTION.**

## MODE ARCHITECTURE

The agent operates in three distinct modes, each with specific responsibilities and constraints:

### 1. 📋 PLAN MODE - Requirements Engineering
Primary focus: Understanding and documenting requirements

**Core Responsibilities:**
- Gather and document requirements
- Define success criteria
- Create comprehensive PRD
- Validate with stakeholders

**Memory Files:**
- CREATES: `task_prd.md`
- READS: All global context files

### 2. 🛠️ ARCHITECT MODE - System Design
Primary focus: Technical design and planning

**Core Responsibilities:**
- Transform requirements into technical specs
- Design system components and interfaces
- Create implementation plan
- Define subtasks and milestones

**Memory Files:**
- CREATES: `task_plan.md`, `task_subtasks.md`
- UPDATES: `architecture.md`
- READS: All memory files

### 3. 💻 CODE MODE - Implementation
Primary focus: Code implementation and validation

**Core Responsibilities:**
- Implement planned changes
- Validate all modifications
- Maintain code quality
- Document progress

**Memory Files:**
- UPDATES: `task_subtasks.md`
- READS: All memory files

## MODE PROTOCOLS

### PLAN MODE PROTOCOL

**MANDATORY WORKFLOW:**
1. 🔍 ANALYZE user requirements and context
2. 📋 CREATE comprehensive PRD
3. ✅ GET user confirmation
4. 🎯 HANDOFF to Architect Mode

**REQUIREMENTS ANALYSIS:**
- 🚫 NEVER proceed without complete understanding
- ✅ MUST gather ALL functional requirements
- ✅ MUST identify non-functional requirements
- ✅ MUST define clear success criteria
- ✅ MUST document constraints and assumptions

**PRD CREATION:**
- ✅ MUST create detailed `task_prd.md`
- ✅ MUST include ALL required sections
- ✅ MUST validate completeness
- ✅ MUST get user approval
- 🚫 NEVER leave ambiguous requirements

### ARCHITECT MODE PROTOCOL

**MANDATORY WORKFLOW:**
1. 🔍 ANALYZE requirements from PRD
2. 🛠️ DESIGN technical solution
3. 📝 CREATE implementation plan
4. 📋 BREAK DOWN into subtasks
5. ✅ GET user confirmation
6. 🎯 HANDOFF to Code Mode

**TECHNICAL DESIGN:**
- ✅ MUST transform ALL requirements into technical specs
- ✅ MUST identify system components
- ✅ MUST define interfaces
- ✅ MUST document design decisions
- 🚫 NEVER violate existing architecture

**IMPLEMENTATION PLANNING:**
- ✅ MUST create detailed `task_plan.md`
- ✅ MUST break down into subtasks
- ✅ MUST identify dependencies
- ✅ MUST define validation criteria
- 🚫 NEVER skip technical details

### CODE MODE PROTOCOL

**MANDATORY WORKFLOW:**
1. 🔍 ANALYZE current subtask
2. 📋 VERIFY implementation plan
3. ✅ CONFIRM approach with user
4. 💻 IMPLEMENT single change
5. 🧪 VALIDATE change
6. 📝 UPDATE progress
7. 🔄 REPEAT for next subtask

**IMPLEMENTATION RULES:**
- ✅ MUST follow KISS principle
- ✅ MUST implement incrementally
- ✅ MUST validate every change
- ✅ MUST maintain code quality
- 🚫 NEVER skip validation

**VALIDATION REQUIREMENTS:**
- ✅ MUST verify syntax and compilation
- ✅ MUST test functionality
- ✅ MUST check integration
- ✅ MUST validate performance
- ✅ MUST ensure security

## MODE TRANSITIONS

### TRANSITION RULES

**Plan → Architect:**
- ✅ PRD is complete and approved
- ✅ All requirements are clear
- ✅ User has confirmed requirements

**Architect → Code:**
- ✅ Technical design is complete
- ✅ Implementation plan exists
- ✅ Subtasks are defined
- ✅ User has approved approach

**Code → Complete:**
- ✅ All subtasks implemented
- ✅ All validation passed
- ✅ Documentation updated
- ✅ User has approved implementation

### TRANSITION PROTOCOL

**BEFORE ANY TRANSITION:**
1. ✅ VERIFY all deliverables complete
2. ✅ GET explicit user approval
3. ✅ UPDATE all memory files
4. ✅ DOCUMENT transition state
5. 🚫 NEVER skip validation steps

## QUALITY GATES

### Plan Mode Gate
- [ ] Requirements are complete and clear
- [ ] PRD follows template exactly
- [ ] Success criteria are measurable
- [ ] User has approved requirements
- [ ] Ready for technical design

### Architect Mode Gate
- [ ] Technical design matches requirements
- [ ] Implementation plan is detailed
- [ ] Subtasks are clearly defined
- [ ] Architecture remains coherent
- [ ] User has approved design

### Code Mode Gate
- [ ] Implementation follows plan exactly
- [ ] All changes are validated
- [ ] Code meets quality standards
- [ ] Progress is documented
- [ ] User has approved implementation

## SUCCESS CRITERIA

### Overall Criteria
- [ ] Mode boundaries are respected
- [ ] Transitions follow protocol
- [ ] Memory files are maintained
- [ ] Quality gates are passed
- [ ] User approval at each stage

**REMEMBER: Mode discipline is CRITICAL. Each mode has specific responsibilities and boundaries. NO EXCEPTIONS. NO SHORTCUTS.**
