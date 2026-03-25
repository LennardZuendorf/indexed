---
type: spec
scope: indexed-config
parent: product.md
updated: 2026-02-19
status: implemented
---

# Product Spec: Config & .env Loading Fix

Fixes real usability issues discovered when using the config system in practice. Users were seeing unexpected behavior around which config and credentials get loaded.

**For technical implementation, see [feature-config-tech.md](feature-config-tech.md).**

---

## User Problems

### 1. Config files were silently merged

When both `~/.indexed/config.toml` (global) and `.indexed/config.toml` (local) existed, the system merged them — producing a hybrid config that didn't match either file. Users set a value in local config expecting it to be the source of truth, but global values leaked through.

**Expected behavior:** The system picks ONE config source. If a local config exists, use it. If not, fall back to global. Never merge.

### 2. Project .env files were ignored

Users expected `CWD/.env` (the standard project-level `.env` file) to be loaded. It wasn't — only `.indexed/.env` files were loaded. This meant credentials placed in the standard project `.env` location had no effect.

**Expected behavior:** Both `.indexed/.env` and `CWD/.env` are loaded. `.indexed/.env` takes priority (it's the indexed-specific location), but `CWD/.env` fills in any gaps. Real environment variables (already set in the shell) override both.

### 3. Accidental .env commits

When using local mode (`.indexed/` in the project directory), there was no `.gitignore` to prevent `.env` files from being committed. Users could accidentally push credentials to git.

**Expected behavior:** When a local `.indexed/` directory is created, it automatically includes a `.gitignore` with `.env` entry. Global `~/.indexed/` doesn't need this (it's outside any git repo).

### 4. Secrets saved to wrong location

During the `indexed index create` workflow, if credentials are missing, the CLI prompts the user to enter them. These secrets were being saved to an `.env` path that didn't match the resolved storage mode — potentially writing to the wrong location.

**Expected behavior:** Secrets are always saved to the `.env` file that matches the effective storage mode (local or global, based on which config was resolved).

---

## Behavior Specification

### Config source resolution

The system always resolves to a single config source. It never merges global and local configs.

| Condition | Config source used |
|-----------|-------------------|
| `--local` flag | `.indexed/config.toml` (local only) |
| `--global` flag | `~/.indexed/config.toml` (global only) |
| Workspace preference set | Whichever mode the preference specifies |
| `.indexed/config.toml` exists | Local (auto-detected) |
| None of the above | Global (default) |

### Credential loading priority

When the same variable appears in multiple locations, the highest-priority source wins:

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | Shell environment | `export JIRA_TOKEN=xxx` |
| 2 | `.indexed/.env` | From the resolved storage root |
| 3 (lowest) | `CWD/.env` | Standard project .env file |

`INDEXED__*` environment variables (e.g., `INDEXED__sources__jira__url`) are always applied on top of the TOML config data, regardless of source.

### Secret persistence during CLI prompts

When the CLI prompts for missing credentials (e.g., during `indexed index create`):
- Sensitive fields (tokens, passwords, API keys) are written to the `.env` file of the **resolved** storage root
- Non-sensitive fields are written to the `config.toml` of the resolved storage root

### .gitignore protection

When a local `.indexed/` directory is created (via `ensure_storage_dirs` or any setup flow):
- A `.gitignore` file is created with `.env` entry
- If `.gitignore` already exists, `.env` is appended (if not already listed)
- This only applies to local `.indexed/` (project directories), not `~/.indexed/` (home directory)

---

## User Flows Affected

### Creating a collection with missing credentials

**Before (broken):**
1. User runs `indexed index create --type jira --name tickets`
2. CLI detects missing Jira API token
3. User enters token when prompted
4. Token saved to wrong `.env` location (defaults to local even when using global mode)
5. Next run: token not found, user prompted again

**After (fixed):**
1. User runs `indexed index create --type jira --name tickets`
2. CLI detects missing Jira API token
3. User enters token when prompted
4. Token saved to `.env` in the resolved storage root (matches where config was loaded from)
5. Next run: token found, no prompt needed

### Working with project-level .env

**Before (broken):**
1. User has `CWD/.env` with `JIRA_TOKEN=xxx` (standard project convention)
2. Runs `indexed index create` — token not found, user prompted again
3. User confused: "I already set it in .env!"

**After (fixed):**
1. User has `CWD/.env` with `JIRA_TOKEN=xxx`
2. Runs `indexed index create` — token loaded from `CWD/.env`
3. Works as expected

### Switching between local and global mode

**Before (broken):**
1. User has both `~/.indexed/config.toml` and `.indexed/config.toml`
2. System merges both — user sees unexpected hybrid values
3. Changing a value in local config doesn't fully "override" because global values still leak through for other keys

**After (fixed):**
1. User has both config files
2. System detects local config → uses local only
3. Global config is completely ignored (no merging)
4. Behavior is predictable: "my local config is exactly what gets used"
