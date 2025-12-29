# Development Guide

This guide covers everything you need to know to set up your development environment, understand the codebase structure, and contribute to Indexed.

## 1. Quick Links

- [**Architecture & Internals**](./architecture-internals.mdx) - Deep dive into the system design, core engine, and configuration system.
- [**CLI Implementation**](./cli-implementation.mdx) - Details on the CLI structure, Rich UI components, and MCP integration.

---

## 2. Core Technologies

Indexed is built on a modern Python stack focused on performance and developer experience.

| Category | Tools |
|----------|-------|
| **Core** | Python 3.11+, FAISS (Vector Search), Sentence Transformers (Embeddings) |
| **CLI** | Typer, Rich, Pydantic |
| **Parsing** | Unstructured (PDF, DOCX, etc.) |
| **Build** | `uv` (Package Manager), `una` (Monorepo), `hatch` |
| **Quality** | `ruff` (Lint/Format), `mypy` (Types), `pytest` (Testing) |

---

## 3. Monorepo Structure

The project is organized as a workspace with multiple packages bundled into a single distribution.

```
indexed/
├── apps/
│   └── indexed/                # Main CLI application entry point
├── packages/
│   ├── indexed-core/           # Core engine, indexing logic, services
│   ├── indexed-config/         # Configuration management system
│   ├── indexed-connectors/     # Data source connectors (Jira, Confluence)
│   └── utils/                  # Shared utilities (logging, batching)
├── tests/                      # Unit and integration tests
├── dist/                       # Built wheels
├── pyproject.toml              # Root workspace configuration
└── uv.lock                     # Dependency lock file
```

---

## 4. Environment Setup

We use **[uv](https://github.com/astral-sh/uv)** for fast, reliable package management.

### Initial Setup

1.  **Install uv:**
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Sync Environment:**
    Install all dependencies (including dev tools) in a virtual environment:
    ```bash
    uv sync --all-groups
    ```

    > **Note:** Always run `uv sync` after pulling changes or modifying `pyproject.toml`.

---

## 5. Development Workflow

### Running Tests

Run the full test suite across all packages:
```bash
uv run pytest -q
```

Run tests for a specific package:
```bash
uv run pytest tests/unit/indexed_core/
```

Generate a coverage report:
```bash
uv run pytest --cov=src --cov-report=html
```

### Code Quality

We use **ruff** for linting and formatting.

```bash
# Check for issues
uv run ruff check .

# Auto-fix issues
uv run ruff check . --fix

# Format code
uv run ruff format
```

### Type Checking

We use **mypy** for static type checking.

```bash
uv run mypy src/
```

### Building the Project

Indexed is distributed as a single wheel that bundles all workspace packages.

**Build from project root:**
```bash
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed
```

This produces a wheel in `dist/` (e.g., `indexed-0.1.0-py3-none-any.whl`) that can be installed via pip.

---

## 6. Dependency Management

-   **Adding a dependency:** Edit the relevant `pyproject.toml` (in root or package subdirectory) and run `uv sync`.
-   **Upgrading dependencies:** Run `uv sync --upgrade`.
-   **Lock file:** The `uv.lock` file ensures reproducible builds. Always commit it.

## 7. Troubleshooting

-   **`ModuleNotFoundError`:** Run `uv sync --all-groups` to ensure packages are installed in editable mode.
-   **Tests failing in CI:** Ensure you are running the full suite with `uv run pytest`.
-   **Wheel build failed:** Ensure you are running the build command from the **project root**, not a subdirectory.
