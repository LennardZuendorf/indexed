# CLI Finalization & Core Cleanup Plan

**Date:** 2025-10-08  
**Status:** 📋 PLANNED  
**Priority:** HIGH

## Overview

Two main objectives:
1. **Finalize CLI Flow & Look** - Revisit UX, add Rich library for polish
2. **Clean Up Core Logging** - Reduce verbosity and noise

## Task 1: Finalize CLI Flow and Look & Feel with Rich

### Goals
- Polish and finalize all CLI commands
- Improve visual output with Rich library
- Ensure consistent, professional UX
- Make it production-ready

### Current State Analysis

**What Works:**
- ✅ All commands functional
- ✅ Clean architecture
- ✅ Type-safe implementation

**What Needs Improvement:**
- ⚠️ Basic text output (no colors, no visual hierarchy)
- ⚠️ No progress indicators during operations
- ⚠️ No spinners for long-running tasks
- ⚠️ Tables could be prettier
- ⚠️ Error messages could be clearer
- ⚠️ No visual feedback during indexing

### Rich Library Features to Use

**1. Console** - Better printing with colors
```python
from rich.console import Console
console = Console()

console.print("[bold green]✓[/bold green] Collection created successfully!")
console.print("[yellow]⚠[/yellow] Warning: No documents found")
console.print("[bold red]✗[/bold red] Error: Collection not found", style="red")
```

**2. Progress Bars** - Show indexing progress
```python
from rich.progress import Progress, SpinnerColumn, TextColumn

with Progress() as progress:
    task = progress.add_task("[cyan]Indexing documents...", total=100)
    while not progress.finished:
        progress.update(task, advance=1)
```

**3. Spinners** - Long operations
```python
from rich.spinner import Spinner
from rich.live import Live

with Live(Spinner("dots", text="Connecting to Jira...")) as live:
    # Do work
    pass
```

**4. Tables** - Better formatting
```python
from rich.table import Table

table = Table(title="Collections", show_header=True)
table.add_column("Name", style="cyan", no_wrap=True)
table.add_column("Documents", justify="right", style="green")
table.add_column("Status", style="yellow")

table.add_row("docs", "13", "✓ Ready")
console.print(table)
```

**5. Panels** - Group related info
```python
from rich.panel import Panel

console.print(Panel(
    "Collection: docs\nDocuments: 13\nChunks: 174",
    title="Collection Details",
    border_style="green"
))
```

**6. Syntax Highlighting** - Code/config display
```python
from rich.syntax import Syntax

config_text = "embedding_model: all-MiniLM-L6-v2"
syntax = Syntax(config_text, "yaml", theme="monokai")
console.print(syntax)
```

### Command-by-Command Improvements

#### `create` Commands

**Before:**
```
Creating collection 'docs' from ./path...
2025-10-08 19:37:19 | INFO | Started "Preparing collection creator"
2025-10-08 19:37:21 | INFO | Finished "Preparing collection creator" in 1.87 seconds
...
✓ Collection 'docs' created
```

**After:**
```
[cyan]Creating collection[/cyan] [bold]docs[/bold] from [dim]./path[/dim]

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Indexing Progress                      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
Reading documents  ━━━━━━━━━━━━━━━━━━ 100% 13/13
Embedding chunks   ━━━━━━━━━━━━━━━━━━ 100% 174/174
Building index     ━━━━━━━━━━━━━━━━━━ 100%

[bold green]✓[/bold green] Collection [bold]docs[/bold] created successfully!
  Documents: 13
  Chunks: 174
  Time: 5.2s
```

#### `search` Command

**Before:**
```
Searching for: memory management
Collection: memory

Collection: memory
Found 8 documents

  ID: README.md
  Score: N/A

  ID: brief.md
  Score: N/A
```

**After:**
```
[cyan]🔍 Searching for:[/cyan] [bold]memory management[/bold]
[dim]Collection: memory[/dim]

╔═══════════════════════════════════════════════════════════╗
║ Search Results                                            ║
╠═══════════════════════════════════════════════════════════╣
║                                                           ║
║ [bold cyan]README.md[/bold cyan]                        [dim]Score: 0.87[/dim] ║
║ Memory management protocol for SWE agents...              ║
║                                                           ║
║ [bold cyan]brief.md[/bold cyan]                         [dim]Score: 0.82[/dim] ║
║ Project brief covering memory persistence...              ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝

Found [bold green]8[/bold green] documents in [dim]0.5s[/dim]
```

#### `inspect` Command

**Before:**
```
Found 3 collection(s):

Name                               Docs   Chunks Updated               
──────────────────────────────────────────────────────────────────────
files                                13      174 2025-10-08T15:56:17.4 
memory                               13      174 2025-10-08T17:39:50.3 
```

**After:**
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Collections                                                ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

╭─────────────┬──────────┬────────┬─────────────────────╮
│ Name        │ Documents│ Chunks │ Updated             │
├─────────────┼──────────┼────────┼─────────────────────┤
│ files       │       13 │    174 │ 2025-10-08 15:56:17 │
│ memory      │       13 │    174 │ 2025-10-08 17:39:50 │
│ test-memory │       13 │    191 │ 2025-10-08 17:24:14 │
╰─────────────┴──────────┴────────┴─────────────────────╯

Total: [bold]3[/bold] collections
```

#### `config show` Command

**Before:**
```
Configuration:

Embedding:
  Model: sentence-transformers/all-MiniLM-L6-v2

Indexing:
  Chunk Size: 512
  ...
```

**After:**
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Configuration                                  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

[bold cyan]Embedding[/bold cyan]
  Model: [green]sentence-transformers/all-MiniLM-L6-v2[/green]

[bold cyan]Indexing[/bold cyan]
  Chunk Size: [yellow]512[/yellow]
  Chunk Overlap: [yellow]50[/yellow]
  Batch Size: [yellow]32[/yellow]

[bold cyan]Search[/bold cyan]
  Max Results: [yellow]10[/yellow]
  Threshold: [yellow]0.7[/yellow]

[bold cyan]Storage[/bold cyan]
  Path: [dim]data/collections[/dim]
```

### Error Handling Improvements

**Before:**
```
Error: Collection 'test' not found
```

**After:**
```
[bold red]✗ Error[/bold red]

Collection [bold]test[/bold] not found.

Available collections:
  • docs
  • memory
  • files

Try: [cyan]indexed-cli inspect[/cyan] to see all collections
```

### Implementation Plan

**Phase 1: Setup Rich Integration**
1. Add `rich` to dependencies
2. Create `cli/utils/console.py` with shared Console instance
3. Create helper functions for common patterns

**Phase 2: Update Commands (Priority Order)**
1. `inspect` - Tables are perfect for this
2. `config show` - Panels and syntax highlighting
3. `create` - Progress bars and spinners
4. `search` - Better result formatting
5. `update` - Progress indicators
6. `delete` - Confirmation prompts with Rich

**Phase 3: Polish**
1. Consistent color scheme throughout
2. Better error messages with context
3. Help text formatting
4. Success/warning/error visual indicators

### Files to Modify

```
apps/indexed-cli/src/cli/
├── utils/
│   ├── console.py          # NEW: Rich Console setup
│   └── formatting.py       # NEW: Formatting helpers
├── commands/
│   ├── create.py           # MODIFY: Add progress bars
│   ├── search.py           # MODIFY: Better result display
│   ├── inspect.py          # MODIFY: Rich tables
│   ├── config.py           # MODIFY: Panels and highlighting
│   ├── update.py           # MODIFY: Progress indicators
│   └── delete.py           # MODIFY: Rich prompts
└── app.py                  # MODIFY: Rich error handling
```

### Color Scheme

**Consistent Colors:**
- `[cyan]` - Command names, section headers
- `[green]` - Success messages, counts
- `[yellow]` - Warnings, metadata
- `[red]` - Errors
- `[dim]` - Less important info (paths, timestamps)
- `[bold]` - Important values (collection names, queries)

### User Feedback

**Progress Indicators for:**
- Reading documents from source
- Chunking text
- Generating embeddings
- Building index
- Searching (if >1s)

**Spinners for:**
- Connecting to remote sources (Jira, Confluence)
- Loading configuration
- Initializing models

## Task 2: Clean Up Core Logging

### Current Issues

**Problem:** Too much logging noise during normal operations
```
2025-10-08 19:37:19 | INFO | ------------------------------------------------------------------
2025-10-08 19:37:19 | INFO | Started "Preparing collection creator"
2025-10-08 19:37:21 | INFO | Finished "Preparing collection creator" in 1.8743 seconds
2025-10-08 19:37:21 | INFO | ------------------------------------------------------------------
2025-10-08 19:37:21 | INFO | Started "Reading documents for collection: test"
...
```

**What Should Be Visible:**
- Errors (always)
- Warnings (always)
- High-level progress (by default)
- Detailed info (only with --verbose)

### Solution: Proper Log Levels

**ERROR** - Always shown
```python
logging.error("Failed to connect to Jira: %s", error)
```

**WARNING** - Always shown
```python
logging.warning("No documents found in collection")
```

**INFO** - Only with --verbose flag
```python
logging.info("Started preparing collection creator")
logging.info("Finished in 1.87 seconds")
```

**DEBUG** - Only with --debug flag
```python
logging.debug("Cache hit for document hash: %s", doc_hash)
logging.debug("Loaded config from: %s", config_path)
```

### Changes Needed

**1. Review Core Services**
```python
# BAD - Too verbose for normal use
logging.info("------------------------------------------------------------------")
logging.info("Started \"Preparing collection creator\"")

# GOOD - Use appropriate levels
logging.debug("Preparing collection creator")  # Only with --debug
# Or show progress via Rich Progress bar instead
```

**2. Add Logging Configuration**
```python
# cli/utils/logging.py
def setup_logging(verbose: bool = False, debug: bool = False):
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"  # Simpler format
    )
```

**3. Update CLI Commands**
```python
@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    debug: bool = typer.Option(False, "--debug"),
):
    setup_logging(verbose=verbose, debug=debug)
```

### Files to Review and Modify

**Core Services to Clean Up:**
```
packages/indexed-core/src/core/v1/engine/
├── services/
│   ├── collection_service.py    # Review logging
│   ├── search_service.py        # Review logging
│   └── inspect_service.py       # Review logging
├── factories/
│   └── create_collection_factory.py  # Too verbose
└── readers/
    └── *.py                     # Review logging
```

**Logging Guidelines:**
- `ERROR`: Real errors that need attention
- `WARNING`: Potential issues but operation continues
- `INFO`: Progress updates (only with --verbose)
- `DEBUG`: Detailed internal info (only with --debug)

### User Experience Goals

**Normal Usage (no flags):**
```bash
$ indexed-cli create files --name docs --path ./docs
Creating collection docs from ./docs

Indexing Progress
Reading documents  ━━━━━━━━━━━━━ 100%
Embedding chunks   ━━━━━━━━━━━━━ 100%

✓ Collection docs created successfully!
```

**Verbose Mode (--verbose):**
```bash
$ indexed-cli create files --name docs --path ./docs --verbose
Creating collection docs from ./docs
INFO: Initializing document reader
INFO: Found 13 files to process
INFO: Chunking documents
INFO: Generated 174 chunks
INFO: Creating embeddings
INFO: Building FAISS index
✓ Collection docs created successfully!
```

**Debug Mode (--debug):**
```bash
$ indexed-cli create files --name docs --path ./docs --debug
Creating collection docs from ./docs
DEBUG: Config loaded from /path/to/indexed.toml
DEBUG: Reader initialized with patterns: *.md, *.txt
DEBUG: Processing file: README.md
DEBUG: File size: 1024 bytes
DEBUG: Chunks created: 3
...
✓ Collection docs created successfully!
```

## Implementation Order

### Priority 1: Core Logging Cleanup
1. Add logging configuration to CLI
2. Review and downgrade noisy INFO logs to DEBUG
3. Clean up separator lines and unnecessary output
4. Test that errors/warnings still show properly

### Priority 2: Rich Integration - Quick Wins
1. Add Rich Console to error messages
2. Update `inspect` command with Rich tables
3. Add success/error/warning styling

### Priority 3: Rich Integration - Progress
1. Add progress bars to `create` commands
2. Add spinners for remote connections
3. Better `search` result formatting

### Priority 4: Polish Everything
1. Consistent color scheme
2. Better help text
3. Interactive confirmations
4. Documentation updates

## Success Metrics

**CLI is finalized when:**
- ✓ All commands have polished output
- ✓ Progress bars for long operations
- ✓ Consistent color scheme
- ✓ Clear error messages with context
- ✓ Professional, production-ready feel

**Core is clean when:**
- ✓ No noise during normal operations
- ✓ Proper log levels throughout
- ✓ Verbose/debug modes work correctly
- ✓ Easy to troubleshoot with --debug

## Estimated Effort

**Core Logging Cleanup:** 2-3 hours
- Review ~10 files
- Update log levels
- Test verbose/debug modes

**Rich Integration:** 4-6 hours
- Setup and helpers: 1h
- Update commands: 3-4h
- Polish and testing: 1-2h

**Total:** ~1 day of focused work

## Dependencies

**New:**
- `rich` - Already available, just need to use it

**Existing:**
- `typer` - Already using
- `logging` - Built-in

## Next Steps

1. Start with core logging cleanup (fastest win)
2. Add Rich to one command as proof-of-concept
3. Roll out to remaining commands
4. Polish and finalize

---

**Ready to make the CLI production-ready! 🚀**
