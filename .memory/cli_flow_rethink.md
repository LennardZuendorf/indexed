# CLI Flow Rethink - Discussion

**Date:** 2025-10-08  
**Status:** 🤔 DISCUSSION

## Current CLI Structure

```
indexed-cli
├── search <query> [--collection NAME] [--limit N]
├── update <collection>
├── delete <collection> [--force]
├── inspect [collection]
├── create
│   ├── files --name NAME --path PATH
│   ├── jira --name NAME --url URL --query QUERY
│   └── confluence --name NAME --url URL --query QUERY
├── config
│   ├── show
│   └── init
└── legacy
```

## User Journey Analysis

### New User First Time Experience

**Goal:** Index some documents and search them

**Current Flow:**
```bash
# 1. Check config (optional)
indexed-cli config show

# 2. Create collection
indexed-cli create files --name docs --path ./documentation

# 3. Search
indexed-cli search "authentication"

# 4. See what's indexed
indexed-cli inspect
```

**Questions to Consider:**
- Is `create <type>` intuitive? Or should it be `add`?
- Should there be a quick-start command?
- Do we need `config init` or should it auto-initialize?
- Is the nested structure (`create files`) clear?

### Common User Workflows

#### Workflow 1: Local Documentation
```bash
indexed-cli create files --name docs --path ./docs
indexed-cli search "how to configure"
```

#### Workflow 2: Jira Issues
```bash
indexed-cli create jira --name jira-proj --url ... --query "project = PROJ"
indexed-cli search "bug in authentication" --collection jira-proj
```

#### Workflow 3: Multiple Sources
```bash
indexed-cli create files --name docs --path ./docs
indexed-cli create jira --name issues --url ... --query "..."
indexed-cli create confluence --name wiki --url ... --query "..."
indexed-cli search "API documentation"  # Searches all
```

#### Workflow 4: Maintenance
```bash
indexed-cli inspect                  # See all collections
indexed-cli inspect docs             # See one collection
indexed-cli update docs              # Refresh with new files
indexed-cli delete old-collection    # Remove
```

## Potential Improvements

### Option 1: Keep Current Structure (Minimal Changes)

**Pros:**
- Already implemented
- Clear separation of concerns
- Follows common CLI patterns

**Cons:**
- `create` might be confusing (vs `add`, `index`, `new`)
- Two-level nesting might be overkill

**Commands:**
```bash
indexed-cli create files --name X --path Y
indexed-cli add files --name X --path Y      # Alternative verb?
indexed-cli index files --name X --path Y    # Alternative verb?
```

### Option 2: Flatten Some Commands

**Idea:** Make common operations top-level

**Commands:**
```bash
# Top-level commands
indexed-cli search <query>
indexed-cli list                    # Instead of inspect with no args
indexed-cli show <collection>       # Instead of inspect <name>

# Grouped commands
indexed-cli add files ...
indexed-cli add jira ...
indexed-cli add confluence ...

indexed-cli remove <collection>     # Instead of delete
indexed-cli update <collection>

indexed-cli config show
indexed-cli config init
```

**Pros:**
- `list` is more intuitive than `inspect` with no args
- `add` might be clearer than `create`
- `show` is more consistent with `config show`

**Cons:**
- More top-level commands
- Less grouping

### Option 3: Resource-Based Structure

**Idea:** Think of collections as resources

**Commands:**
```bash
# Collection management
indexed-cli collection add files --name X --path Y
indexed-cli collection add jira --name X --url Y --query Z
indexed-cli collection list
indexed-cli collection show <name>
indexed-cli collection update <name>
indexed-cli collection remove <name>

# Search (top-level, most common operation)
indexed-cli search <query> [--collection NAME]

# Config
indexed-cli config show
indexed-cli config init
```

**Pros:**
- Clear resource namespace (collection)
- Search at top-level (most important)
- Consistent verbs (add, list, show, update, remove)

**Cons:**
- Longer commands
- More typing

### Option 4: Git-Style (Short + Long Forms)

**Idea:** Provide both short and descriptive forms

**Commands:**
```bash
# Short forms (for power users)
indexed-cli add <type> ...    # Create collection
indexed-cli rm <name>         # Remove collection  
indexed-cli ls                # List collections
indexed-cli up <name>         # Update collection

# Long forms (for clarity)
indexed-cli create <type> ...
indexed-cli delete <name>
indexed-cli list
indexed-cli update <name>

# Always clear
indexed-cli search <query>
indexed-cli show <collection>
```

**Pros:**
- Flexibility for different users
- Power users can be efficient
- New users can use descriptive commands

**Cons:**
- Two ways to do everything
- More maintenance

## Verb Consistency Analysis

### Current Verbs
- `create` - Add new collection
- `search` - Search collections
- `update` - Refresh collection
- `delete` - Remove collection
- `inspect` - View collection(s) info
- `show` - View config
- `init` - Initialize config

### Potential Better Verbs

**Collections:**
- `create` / `add` / `index` / `new`
- `delete` / `remove` / `rm`
- `update` / `refresh` / `sync`
- `inspect` / `show` / `describe` / `info`
- `list` / `ls` (for all collections)

**Search:**
- `search` / `query` / `find`

**Config:**
- `show` / `get` / `display`
- `init` / `setup` / `create`

## Command Organization Patterns

### Pattern A: Flat (Docker-style)
```bash
indexed-cli search
indexed-cli create
indexed-cli list
indexed-cli update
indexed-cli remove
```

### Pattern B: Grouped (kubectl-style)
```bash
indexed-cli collection create
indexed-cli collection list
indexed-cli collection update
indexed-cli collection delete
indexed-cli search
```

### Pattern C: Hybrid (git-style)
```bash
indexed-cli search        # Top-level for common
indexed-cli create ...    # Top-level for common
indexed-cli collection list
indexed-cli collection show
indexed-cli config show
```

## Questions for Decision

### 1. Command Naming
- **Q:** Should collections be `create`d, `add`ed, or `index`ed?
- **Options:**
  - `create` - Creates a new collection
  - `add` - Adds documents to index
  - `index` - More explicit about what it does
  
### 2. Inspection Commands
- **Q:** How should users view collections?
- **Options:**
  - `inspect` / `inspect <name>` (current)
  - `list` / `show <name>`
  - `collection list` / `collection show <name>`

### 3. Grouping Strategy
- **Q:** Should related commands be grouped?
- **Options:**
  - Flat: `indexed-cli create`, `indexed-cli list`
  - Grouped: `indexed-cli collection create`, `indexed-cli collection list`
  - Hybrid: Common flat, others grouped

### 4. Aliases
- **Q:** Should we support short aliases?
- **Options:**
  - No aliases (explicit only)
  - Standard aliases (`ls`, `rm`)
  - Full aliasing system

## Real-World CLI Comparisons

### Docker CLI
```bash
docker ps                 # List
docker images             # List different resource
docker run ...            # Create/start
docker rm ...             # Remove
docker inspect ...        # Detailed info
```
**Pattern:** Flat structure, short verbs, different commands for different resources

### kubectl
```bash
kubectl get pods          # List
kubectl describe pod X    # Detailed info
kubectl create ...        # Create
kubectl delete pod X      # Remove
```
**Pattern:** Grouped by resource, consistent verbs (get, describe, create, delete)

### Git
```bash
git status               # See state
git add ...              # Stage
git commit ...           # Commit
git log                  # History
```
**Pattern:** Flat, focused on workflow, short verbs

### AWS CLI
```bash
aws s3 ls                # List
aws s3 cp ...            # Copy
aws ec2 describe-instances  # Detailed info
```
**Pattern:** Service-grouped, then verb or resource-verb

## Recommendation Areas

### Area 1: Search (Clear Winner)
**Keep:** `indexed-cli search <query> [--collection NAME]`
- Most important operation
- Simple and clear
- Top-level makes sense

### Area 2: Collection Management (Needs Decision)

**Option A - Current:**
```bash
indexed-cli create files --name X --path Y
indexed-cli inspect
indexed-cli inspect <name>
indexed-cli update <name>
indexed-cli delete <name>
```

**Option B - More Intuitive:**
```bash
indexed-cli add files --name X --path Y       # "add" feels more natural
indexed-cli list                              # clearer than inspect with no args
indexed-cli show <name>                       # consistent with config show
indexed-cli update <name>                     # keep
indexed-cli remove <name>                     # more standard than delete
```

**Option C - Grouped:**
```bash
indexed-cli collection add files --name X --path Y
indexed-cli collection list
indexed-cli collection show <name>
indexed-cli collection update <name>
indexed-cli collection remove <name>
```

### Area 3: Configuration (Current is Good)
**Keep:**
```bash
indexed-cli config show
indexed-cli config init
```

## Proposed Final Structure (Recommendation)

### Option: Refined Hybrid Approach

```bash
# Most common operations - top level
indexed-cli search <query> [--collection NAME]
indexed-cli list                                    # List all collections

# Collection management - slightly grouped
indexed-cli add files --name X --path Y             # Add collection
indexed-cli add jira --name X --url Y --query Z
indexed-cli add confluence --name X --url Y --query Z

indexed-cli show <collection>                       # Detailed info
indexed-cli update <collection>                     # Refresh
indexed-cli remove <collection> [--force]           # Delete

# Configuration - grouped (less common)
indexed-cli config show
indexed-cli config init [options]

# Advanced/debugging
indexed-cli --verbose ...                           # Verbose output
indexed-cli --debug ...                             # Debug mode
```

**Changes from current:**
- `create` → `add` (more intuitive)
- `inspect` (no args) → `list` (clearer)
- `inspect <name>` → `show <name>` (consistent)
- `delete` → `remove` (more standard)

**Benefits:**
- Common operations simple and short
- Verbs are more intuitive
- Consistent patterns
- Less typing for common tasks

## Decision Needed

**Which structure do you prefer?**

1. **Keep Current** - Minimal changes, already working
2. **Refined Hybrid** - Better verbs (`add`, `list`, `show`, `remove`)
3. **Fully Grouped** - Everything under namespaces (`collection`, `config`)
4. **Custom** - Mix and match from options above

**Key Questions:**
- Do you prefer `create` or `add` for collections?
- Do you want `inspect` or `list`/`show` split?
- Should commands be flat or grouped?
- Do we need command aliases?

---

**Let's discuss and finalize the CLI structure! 🚀**
