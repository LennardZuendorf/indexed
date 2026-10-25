"""Core-engine error types for version detection and routing (core-v2/1).

All inherit the project's :class:`~indexed.config.errors.IndexedError` (via the
:class:`CoreError` base) so the existing CLI exit-code mapping and MCP error
envelopes keep working unchanged.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from indexed.config.errors import IndexedError


class CoreError(IndexedError):
    """Base for core-engine detection/routing errors."""


class EngineMismatchError(CoreError):
    """An explicit engine selector conflicts with a collection's detected engine.

    Raised before any I/O so a mismatched ``--engine`` can never touch a
    collection built by a different engine.
    """

    def __init__(self, collection: str, *, found: str, requested: str) -> None:
        self.collection = collection
        self.found = found
        self.requested = requested
        super().__init__(
            f"Collection '{collection}' is a v{found} collection "
            f"but engine v{requested} was requested. "
            f"Re-run without --engine, use --engine v{found}, or migrate it: "
            f"indexed index migrate {collection}"
        )


class UnknownEngineVersionError(CoreError):
    """A manifest's ``version`` marker is an unsupported value.

    Fails loud (R1) and leaves the collection untouched.
    """

    def __init__(
        self,
        *,
        found: object,
        path: object | None = None,
        supported: Sequence[str] = ("1", "2"),
    ) -> None:
        self.found = found
        self.path = path
        self.supported = tuple(supported)
        location = f" at '{path}'" if path is not None else ""
        supported_str = ", ".join(self.supported)
        super().__init__(
            f"Collection manifest{location} declares unknown engine version "
            f"{found!r}. Supported versions: {supported_str}. "
            f"The collection was not modified."
        )


class CoreV2Error(CoreError):
    """A core.v2 engine operation failed.

    Wraps upstream (LlamaIndex) exceptions at the v2 service boundary, which
    have no stable hierarchy (tech.md §Errors), so every failure still inherits
    :class:`~indexed.config.errors.IndexedError` (CLI exit codes + MCP
    envelopes keep working).
    """


# Failure categories for embedding-model acquisition, each with its own
# honest remedy. Kept next to the error so the message stays self-contained.
_ACQUISITION_LABEL: dict[str, str] = {
    "network": "network failure",
    "rate_limit": "rate limited",
    "auth": "authentication required",
    "missing": "model not found",
    "corrupt": "corrupt or incomplete local model",
    "unknown": "unexpected error",
}

_ACQUISITION_REMEDY: dict[str, str] = {
    "network": (
        "Check your network, proxy, or VPN and retry; once online, run "
        "'indexed init --model {model}' to download it."
    ),
    "rate_limit": (
        "The Hugging Face Hub is rate-limiting requests; wait a moment and "
        "retry, or authenticate to raise the limit."
    ),
    "auth": (
        "The model repository may be gated: accept its license on "
        "huggingface.co and authenticate (for example with 'hf auth login'), "
        "then retry."
    ),
    "missing": "Verify the model name, then run 'indexed init --model {model}'.",
    "corrupt": (
        "Run 'indexed init --force --model {model}' to re-download the model, "
        "then retry."
    ),
    "unknown": (
        "Run 'indexed init --model {model}' to (re)download the model, then retry."
    ),
}


class ModelAcquisitionError(CoreError):
    """An embedding model could not be acquired (downloaded or loaded).

    The single actionable diagnostic every surface shows instead of dependency
    retry chatter: it names the model, the local HuggingFace cache and its
    state, the failure category, and a category-specific remedy. Raised at the
    acquisition seam in ``core.v1``'s ``model_manager`` and ``core.v2``'s
    ``embedding.local``; inherits ``IndexedError`` so the CLI exit code and MCP
    error envelope keep working unchanged.
    """

    def __init__(
        self,
        model: str,
        *,
        action: str,
        category: str,
        cache_dir: object,
        cache_state: str,
        attempts: int = 1,
        cause: str | None = None,
    ) -> None:
        self.model = model
        self.action = action
        self.category = category
        self.cache_dir = cache_dir
        self.cache_state = cache_state
        self.attempts = attempts
        label = _ACQUISITION_LABEL.get(category, category)
        attempt_note = f" after {attempts} attempts" if attempts > 1 else ""
        cause_note = f": {cause}" if cause else ""
        remedy = _ACQUISITION_REMEDY.get(
            category, _ACQUISITION_REMEDY["unknown"]
        ).format(model=model)
        super().__init__(
            f"Embedding model '{model}' could not be {action}ed{attempt_note} "
            f"({label}{cause_note}). Cache: {cache_dir} ({cache_state}). {remedy}"
        )


class CollectionRecoveryError(CoreError):
    """A collection's on-disk generations could not be proven restorable.

    Raised when an EXPLICITLY requested collection was stranded by an
    interrupted replace and recovery could not restore a complete generation.
    The data is never deleted: recovery moves it to
    ``<collections>/.recovery/<name>/``. Fails loud because silently omitting
    the collection would read as "no such collection" and the preserved data
    would never be found.
    """

    def __init__(
        self,
        collection: str,
        *,
        reason: str,
        quarantine_path: object | None = None,
    ) -> None:
        self.collection = collection
        self.reason = reason
        self.quarantine_path = quarantine_path
        where = (
            f" Its data is preserved under '{quarantine_path}'."
            if quarantine_path is not None
            else ""
        )
        super().__init__(
            f"Collection '{collection}' could not be recovered: {reason}.{where} "
            f"Inspect that directory and move it back by hand, or rebuild the "
            f"collection with 'indexed index create'."
        )


class UnknownVectorStoreError(CoreError):
    """A v2 collection records a vector store this installation can't load.

    Raised by :func:`indexed.core.v2.stores.load_storage_context` when the
    manifest's ``engine.vectorStore`` is not one this build supports. The
    engine fails loud (R9) and NEVER silently substitutes another store, so a
    collection built for a future store is never mis-read as ``simple``.
    """

    def __init__(self, store: object, *, known: Iterable[str]) -> None:
        self.store = store
        self.known = tuple(known)
        known_str = ", ".join(sorted(self.known))
        super().__init__(
            f"Collection manifest records vector store {store!r}, which this "
            f"installation cannot load. Supported stores: {known_str}. "
            f"The collection was not modified."
        )


__all__ = [
    "CollectionRecoveryError",
    "CoreError",
    "CoreV2Error",
    "EngineMismatchError",
    "ModelAcquisitionError",
    "UnknownEngineVersionError",
    "UnknownVectorStoreError",
]
