# CLI Final Design - Complete Specification

**Date:** 2025-10-08  
**Status:** ✅ FINAL DESIGN  
**Version:** 2.0

## Design Philosophy

### Core Principles

1. **Interactive First, Automation Supported**
   - Default experience is conversational and guided
   - Support non-interactive mode for scripts/CI/CD
   - Flags pre-fill prompts but don't skip interaction

2. **Search-First, Not Collection-First**
   - Users want to search, not manage collections
   - Collections are implementation details
   - Search across everything by default

3. **Show What's Real, Not What's Imagined**
   - Display actual matched text chunks
   - No AI-generated summaries (unless explicitly requested)
   - Honest about what the index contains

4. **Professional, Not Flashy**
   - Minimal colors (bold, dim, accent only)
   - Clean panels and tables
   - Subtle borders and spacing

5. **Progressive Disclosure**
   - Simple commands by default
   - Advanced options available but not required
   - Tips guide users to more features

## Command Structure

```
indexed
├── search <query>          # Search all documents
├── add                     # Add documents (interactive)
├── list                    # List collections
├── remove <name>           # Remove collection
├── init                    # Initialize setup
└── config                  # Show/edit configuration
```

**6 commands total. That's it.**

---

## Commands - Detailed Specification

### 1. `indexed search <query>`

**Purpose:** Search across all indexed documents

**Usage:**
```bash
indexed search <query> [OPTIONS]
```

**Behavior:**
- Searches ALL collections by default
- Shows actual matched text chunks (not summaries)
- Results are actionable (can copy, open, etc.)

**Options:**

**Output Control:**
- `--limit, -l INT` - Number of results (default: 5)
- `--full` - Show complete matched sections
- `--compact` - Minimal output (titles only)
- `--json` - JSON output

**Interaction:**
- `--open, -o` - Interactive result browser
- `--copy, -c [N]` - Copy result to clipboard

**Filtering:**
- `--collection, -C TEXT` - Search specific collection
- `--since TEXT` - Results updated since (e.g., "1d", "2h")

**Examples:**

```bash
# Simple search - most common use case
indexed search "authentication"

# Specific collection
indexed search "bug" --collection jira

# Show more results
indexed search "API" --limit 10

# Full matched text
indexed search "config" --full

# Interactive browsing
indexed search "auth" --open

# Copy to clipboard
indexed search "auth" --copy
```

**Output (Default):**

```
🔍 Searching: authentication methods

╭─ README.md ─────────────────────────────────────────────╮
│ docs · Score: 0.87 · ./docs/README.md · 2min ago       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ...methods include OAuth 2.0 for web applications,     │
│ API keys for server-to-server communication, and       │
│ JWT tokens for mobile apps. Each method requires       │
│ different configuration. OAuth needs client_id and     │
│ client_secret in environment variables. API keys       │
│ can be generated from the admin dashboard under        │
│ Settings > API Keys. JWT tokens are issued after...    │
│                                                         │
╰─────────────────────────────────────────────────────────╯

╭─ api_guide.md ──────────────────────────────────────────╮
│ docs · Score: 0.82 · ./docs/api_guide.md · 5min ago    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ...API authentication requires passing your API key    │
│ in the Authorization header like this:                 │
│                                                         │
│   Authorization: Bearer YOUR_API_KEY                   │
│                                                         │
│ The authentication system validates tokens against     │
│ the user database. Invalid tokens return 401. Keys    │
│ expire after 90 days and must be rotated...           │
│                                                         │
╰─────────────────────────────────────────────────────────╯

Found 8 results in 0.5s

Use --full for complete matches, --open to browse interactively
```

**Key Features:**
- Shows substantial text chunks (8-10 lines)
- Real matched content, not AI summaries
- Multiple results visible at once
- Helpful metadata (score, location, time)
- Tips for other modes

**Interactive Mode (`--open`):**

```bash
indexed search "authentication" --open
```

```
╭────────────── Search Results ───────────────╮
│                                             │
│  Found 8 results                            │
│                                             │
│  1. README.md            0.87   docs        │
│  2. api_guide.md         0.82   docs        │
│  3. JIRA-1234           0.78   jira         │
│  4. confluence-page      0.76   wiki        │
│  ...                                        │
│                                             │
╰─────────────────────────────────────────────╯

Choose result (1-8, or Q to quit): 1

╭─ README.md ─────────────────────────────────╮
│ [Full matched text shown here]             │
╰─────────────────────────────────────────────╯

Actions: [N]ext [P]rev [C]opy [O]pen file [Q]uit
Action: _
```

---

### 2. `indexed add`

**Purpose:** Add documents to search index

**Usage:**
```bash
indexed add [OPTIONS]
```

**Behavior:**
- **Interactive by default** - Asks what you want to add
- **Supports both modes:**
  - No flags → Full interactive experience
  - Some flags → Pre-fill, prompt for rest
  - All flags + `--yes` → Non-interactive (for scripts)

**Options:**

**Source Selection:**
- `--type TEXT` - Source type: `files`, `jira`, `confluence`
- `--name TEXT` - Collection name

**Files:**
- `--path TEXT` - Path to files/folder
- `--include TEXT` - Include patterns (comma-separated)
- `--exclude TEXT` - Exclude patterns

**Jira/Confluence:**
- `--url TEXT` - Server URL
- `--query TEXT` - JQL/CQL query

**Automation:**
- `--yes, -y` - Skip confirmations (for scripts)

**Examples:**

```bash
# Fully interactive (most common)
indexed add

# Pre-fill type, ask for rest
indexed add --type files

# Pre-fill everything, still confirm
indexed add --name docs --type files --path ./docs

# Non-interactive (for scripts)
indexed add --name docs --type files --path ./docs --yes
```

**Interactive Flow (Default):**

```
What would you like to add?

  1. Local files or folder
  2. Jira project
  3. Confluence space

Choice: 1

📂 Add Local Files

Name for this collection: docs
Path to files or folder [.]: ./documentation
Include patterns (optional, e.g., *.md, *.txt): *.md
Exclude patterns (optional): 

✓ Found 13 markdown files

Ready to index 13 files as "docs"
Continue? (Y/n): y

Indexing documents...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 13/13

✓ Added "docs" with 13 documents (174 chunks)
```

**Semi-Interactive (Some Flags):**

```bash
indexed add --type files --path ./docs
```

```
📂 Add Local Files

Type: files (from --type)
Path: ./docs (from --path)

Name for this collection: documentation
Include patterns (optional): *.md
Exclude patterns (optional): 

✓ Found 13 files
Continue? (Y/n): y

[Progress bar...]
✓ Added "documentation"
```

**Non-Interactive (Full Flags + --yes):**

```bash
indexed add --name docs --type files --path ./docs --yes
```

```
✓ Found 13 files
Indexing... ━━━━━━━━━━━━━━━━━━━ 100%
✓ Added "docs" with 13 documents
```

**Key Features:**
- Conversational flow for humans
- Smart pre-filling with flags
- Always shows what's happening
- Confirmation before long operations
- Script-friendly with `--yes`

---

### 3. `indexed list`

**Purpose:** Show all indexed collections

**Usage:**
```bash
indexed list [OPTIONS]
```

**Options:**
- `--verbose, -v` - Show detailed info
- `--json` - JSON output

**Examples:**

```bash
# Simple list
indexed list

# Detailed view
indexed list --verbose

# JSON (for scripts)
indexed list --json
```

**Output (Default):**

```
╭────────── Indexed Collections ──────────╮
│                                         │
│  docs          13 docs      just now    │
│  memory        13 docs      5min ago    │
│  jira-proj     45 docs      1h ago      │
│                                         │
│  Total: 71 documents                    │
╰─────────────────────────────────────────╯
```

**Output (Verbose):**

```
╭────────── Indexed Collections ──────────╮
│                                         │
│  docs                                   │
│    Type: Local files                    │
│    Path: ./docs                         │
│    Documents: 13                        │
│    Chunks: 174                          │
│    Size: 145 KB                         │
│    Updated: just now                    │
│                                         │
│  memory                                 │
│    Type: Local files                    │
│    Path: ./.memory                      │
│    Documents: 13                        │
│    Chunks: 174                          │
│    Size: 592 KB                         │
│    Updated: 5min ago                    │
│                                         │
│  Total: 26 documents, 348 chunks        │
╰─────────────────────────────────────────╯
```

---

### 4. `indexed remove <name>`

**Purpose:** Remove a collection

**Usage:**
```bash
indexed remove <name> [OPTIONS]
```

**Options:**
- `--force, -f` - Skip confirmation

**Examples:**

```bash
# With confirmation (default)
indexed remove docs

# Skip confirmation (scripts)
indexed remove docs --force
```

**Interactive Confirmation (Default):**

```
⚠️  Remove "docs"?

This will delete:
  • 13 documents
  • 174 chunks
  • All indexed data

This cannot be undone.

Continue? (y/N): _
```

If yes:
```
Removing collection...
✓ Removed "docs"
```

If no:
```
Cancelled
```

**Non-Interactive:**

```bash
indexed remove docs --force
```

```
✓ Removed "docs"
```

---

### 5. `indexed init`

**Purpose:** First-time setup

**Usage:**
```bash
indexed init [OPTIONS]
```

**Options:**
- `--storage PATH` - Storage location
- `--embedding TEXT` - Embedding model
- `--yes, -y` - Use defaults

**Examples:**

```bash
# Interactive setup
indexed init

# Quick setup with defaults
indexed init --yes

# Custom storage
indexed init --storage /custom/path
```

**Interactive Flow (Default):**

```
🚀 Initialize Indexed

Set up your local document search index.

Storage location [~/.indexed/data]: 
Embedding model [all-MiniLM-L6-v2]: 
Chunk size [512]: 

✓ Created storage directory
✓ Initialized configuration
✓ Ready to use!

Next: indexed add
```

**Quick Setup (--yes):**

```bash
indexed init --yes
```

```
✓ Storage: ~/.indexed/data
✓ Model: all-MiniLM-L6-v2
✓ Ready!
```

---

### 6. `indexed config`

**Purpose:** View or edit configuration

**Usage:**
```bash
indexed config [OPTIONS]
```

**Options:**
- `--edit, -e` - Edit interactively
- `--set KEY=VALUE` - Set specific value
- `--json` - JSON output

**Examples:**

```bash
# Show config
indexed config

# Edit interactively
indexed config --edit

# Quick edit
indexed config --set chunk_size=1024

# JSON output
indexed config --json
```

**Output (Default):**

```
╭─────────── Configuration ───────────╮
│                                     │
│  Storage     ~/.indexed/data        │
│  Embedding   all-MiniLM-L6-v2       │
│  Chunk size  512 characters         │
│  Batch size  32                     │
│                                     │
│  Edit: indexed config --edit        │
╰─────────────────────────────────────╯
```

**Interactive Edit (`--edit`):**

```
╭──────── Edit Configuration ────────╮
│                                    │
│  1. Storage path    ~/.indexed     │
│  2. Embedding       all-MiniLM...  │
│  3. Chunk size      512            │
│  4. Chunk overlap   50             │
│  5. Batch size      32             │
│  6. Max results     10             │
│  7. Threshold       0.7            │
│                                    │
│  8. Save and exit                  │
│  9. Cancel                         │
│                                    │
╰────────────────────────────────────╯

Edit setting (1-9): 3

Chunk size [512]: 1024
✓ Updated

Edit setting (1-9): 8

✓ Configuration saved
```

---

## Global Options

Work with any command:

```bash
indexed [GLOBAL_OPTIONS] <command> [OPTIONS]
```

**Available globally:**
- `--verbose, -v` - Show detailed progress/logs
- `--debug` - Show debug information
- `--quiet, -q` - Minimal output (errors only)
- `--help, -h` - Show help
- `--version` - Show version

**Examples:**

```bash
# Verbose mode
indexed --verbose search "query"

# Debug mode
indexed --debug add

# Quiet mode
indexed --quiet list
```

---

## Visual Design

### Color Palette (Minimal)

**Use sparingly:**
- **Bold** - Important info (names, numbers)
- **Dim** - Secondary info (timestamps, paths, borders)
- **Cyan** - Interactive prompts only
- **Yellow** - Warnings only
- **Green** - Success messages only
- **Red** - Errors only

**No colors for:**
- Regular text
- Search results content
- Most output

### Typography

- **Bold:** Collection names, important numbers
- **Dim:** Metadata, borders, less important info
- **Regular:** Everything else (most text)

### Layout

- **Panels:** Rounded borders (`box.ROUNDED`)
- **Tables:** Simple borders or no borders
- **Spacing:** Generous padding (1-2 chars in panels)
- **Clean:** Empty lines between sections

### Example Styling

```python
from rich.console import Console
from rich.panel import Panel
from rich import box

console = Console()

# Search result - minimal styling
panel = Panel(
    matched_text,  # Just the text, no fancy formatting
    title=f"[bold]{doc_id}[/bold]",
    subtitle=f"[dim]{collection} · Score: {score:.2f} · {time}[/dim]",
    border_style="dim",  # Subtle border
    box=box.ROUNDED,     # Softer corners
    padding=(1, 2)       # Breathing room
)
console.print(panel)
```

---

## Logging Strategy

### Default Mode (No Flags)
- Show: Progress bars, results, errors
- Hide: All debug/info logs
- Clean output, no noise

### Verbose Mode (`--verbose`)
- Show: High-level operations
- Format: Simple messages
```
INFO: Reading 13 files
INFO: Generating embeddings
INFO: Building index
```

### Debug Mode (`--debug`)
- Show: Everything
- Format: Detailed messages
```
DEBUG: Config loaded from ~/.indexed/config.toml
DEBUG: Processing file: README.md (1.2 KB)
DEBUG: Generated 3 chunks
DEBUG: Embedding dimension: 384
```

### Implementation

```python
# cli/utils/logging.py
import logging
from rich.logging import RichHandler

def setup_logging(verbose=False, debug=False):
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(
            show_time=False,
            show_path=False,
            markup=True
        )]
    )
```

---

## Help Text

### Main Help

```bash
indexed --help
```

```
indexed - Simple document search

USAGE
  indexed <command> [options]

COMMANDS
  search <query>      Search all documents
  add                 Add documents (interactive)
  list                Show collections
  remove <name>       Remove collection
  init                First-time setup
  config              Show/edit configuration

GLOBAL OPTIONS
  -v, --verbose       Show detailed progress
  --debug             Show debug info
  -q, --quiet         Minimal output
  -h, --help          Show help
  --version           Show version

EXAMPLES
  indexed search "authentication"
  indexed add
  indexed list

Get started: indexed init
```

### Command Help

Each command has detailed help:

```bash
indexed search --help
indexed add --help
indexed list --help
# etc.
```

Shows:
- Purpose
- Usage pattern
- All options
- Examples
- Tips

---

## User Workflows

### New User First Time

```bash
# 1. Initialize
$ indexed init
Storage location [~/.indexed/data]: ↵
✓ Ready!

# 2. Add documents
$ indexed add
What would you like to add?
  1. Local files
Choice: 1
Name: docs
Path: ./documentation
✓ Added "docs" with 13 documents

# 3. Search
$ indexed search "getting started"
[Results...]
```

### Daily Usage

```bash
# Quick search (most common)
indexed search "authentication"

# Add more docs
indexed add --type files
> Name: project-notes
> Path: ./notes
> ✓ Added

# See what's indexed
indexed list
```

### Power User

```bash
# Search with options
indexed search "API" --collection docs --limit 20

# Non-interactive add
indexed add --name wiki --type confluence \
  --url https://... --query "..." --yes

# Copy search result
indexed search "config" --copy
```

### Scripting/CI

```bash
#!/bin/bash

# Initialize
indexed init --yes

# Add docs
indexed add --name docs --type files \
  --path ./docs --yes

# Search (JSON output)
indexed search "error" --json > results.json

# List (JSON output)
indexed list --json > collections.json
```

---

## Key Differences from Original Design

### What Changed

1. **Interactivity**
   - NOW: Interactive by default, non-interactive supported
   - BEFORE: Flag-only by default

2. **Search Results**
   - NOW: Show actual matched text chunks
   - BEFORE: Tried to show AI summaries/explanations

3. **Config Editing**
   - NOW: Interactive menu editor with `--edit`
   - BEFORE: View only

4. **Command Count**
   - NOW: 6 commands (removed `update`, simplified `inspect` to `list`)
   - BEFORE: 7-8 commands

5. **Visual Style**
   - NOW: Minimal colors (bold/dim only, accent colors sparingly)
   - BEFORE: More colorful

### What Stayed

- Search-first philosophy
- Clean, professional output
- Rich library for formatting
- Progressive disclosure
- Multiple modes (default/full/open)

---

## Implementation Priority

### Phase 1: Foundation (Week 1)
1. Setup Rich utilities (console, logging)
2. Implement `indexed search` (default mode)
3. Implement `indexed list`
4. Clean up core logging (hide noise)

### Phase 2: Interactivity (Week 1-2)
1. Implement `indexed add` (fully interactive)
2. Implement `indexed remove` (with confirmation)
3. Implement `indexed init` (interactive setup)
4. Add progress bars to indexing

### Phase 3: Polish (Week 2)
1. Implement `indexed config --edit`
2. Add `indexed search --open` (interactive browse)
3. Add `indexed search --copy`
4. Fine-tune styling and spacing
5. Test all workflows

---

## Success Criteria

**CLI is successful when:**
- ✅ New users can search in <2 minutes
- ✅ Common workflows need 1-2 commands
- ✅ No logging noise by default
- ✅ Output is clean and professional
- ✅ Interactive mode feels natural
- ✅ Script mode works reliably
- ✅ Search results are actionable

---

## Future Enhancements

**Not in v2.0, but planned:**

1. **LLM Integration** (Optional)
   - `indexed search "query" --explain` - AI summary of results
   - `indexed search "query" --chat` - Ask questions about results

2. **Advanced Search**
   - `indexed search "query" --filter "key:value"`
   - `indexed search "query" --date-range "1w"`

3. **Collection Management**
   - `indexed update <name>` - Refresh collection
   - `indexed show <name>` - Detailed collection info

4. **Interactive Shell**
   - `indexed` (no command) - Start interactive shell
   - TAB completion
   - Search history

---

**This is the final design specification! 🚀**
