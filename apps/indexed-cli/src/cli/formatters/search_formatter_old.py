from __future__ import annotations

from typing import Iterable, List, Optional

from cli.utils.rich_console import console
from core.v1.engine.services import SearchResult


def _pick_title(result: SearchResult) -> str:
    """Choose a human-friendly title for a search result.

    Preference order: url > path > id
    """
    return result.url or result.path or result.id


def _format_score(score: Optional[float]) -> str:
    if score is None:
        return "-"
    try:
        return f"{float(score):.3f}"
    except Exception:
        return "-"


def _extract_preview_text(chunk: dict) -> str:
    # Be defensive about possible keys
    text = (
        chunk.get("text")
        or chunk.get("content")
        or chunk.get("chunk")
        or ""
    )
    # Normalize whitespace and truncate
    text = " ".join(str(text).split())
    max_len = 180
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def render_search_results(results: Iterable[SearchResult], *, include_chunks: bool = False) -> None:
    """Render human-readable search results to the console.

    - Prints a compact header summarizing counts
    - One line per document: "n. title (score)"
    - Optionally prints up to 3 matched chunk previews per document
    """
    items: List[SearchResult] = list(results)
    if not items:
        console.print("\n🔎 No results found\n")
        return

    # Summary header
    collection_names = {r.collection_name for r in items if r.collection_name}
    console.print(
        f"\n🔎 Search results: {len(items)} document(s) across {len(collection_names)} collection(s)\n"
    )

    # Per-document lines
    for idx, r in enumerate(items, start=1):
        title = _pick_title(r)
        score = _format_score(r.score)
        console.print(f"{idx}. {title} ({score})")

        # Optional chunk previews
        if include_chunks and r.matched_chunks:
            previews = r.matched_chunks[:3]
            for mc in previews:
                preview = _extract_preview_text(mc)
                console.print(f"   • {preview}")

    console.print()


