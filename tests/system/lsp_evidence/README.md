# LSP Tier 1 evidence: stdio transcripts and golden payloads

These files are the acceptance artifacts for the three methods Tier 1 adds or
changes: `textDocument/definition`, `textDocument/references` and
`publishDiagnostics`. They are **not** hand-written. Each one is captured by
`tests/system/test_lsp_out_of_process.py` from the real server process —
`python -m indexed.cli.app --local lsp` — speaking JSON-RPC 2.0 over
stdin/stdout with `Content-Length` framing, and each one is **asserted on every
test run**. A capability that drifts changes the diff of a committed file; a
capability with no transcript has no evidence.

```
transcripts/definition.json    full session: initialize → 2 × definition → shutdown → exit
transcripts/references.json    full session: initialize → references → [] case → shutdown → exit
transcripts/diagnostics.json   full session: initialize → didOpen/didSave/didClose + the 3 pushes
golden/definition.json         requests + results for both definition calls
golden/references.json         request + result (and the empty-answer case is in the transcript)
golden/diagnostics.json        each document event paired with the notification it produced
```

## Provenance

Captured 2026-11-10 against `feat/241-diagnostics` at
`5e7838433ebaac096e6df8768d4f8570d208c073` (PR #302), the head of the open Tier 1
stack `#252 → #299 → #300 → #301 → #302`. Nothing in that stack is in `main`
yet, so the branch — not `main` — is what these goldens describe.

Client capabilities declared in `initialize` are what a real editor declares:

```json
{"capabilities": {"textDocument": {"publishDiagnostics": {}}}}
```

A client that declares nothing receives no diagnostics at all (asserted in
`tests/unit/indexed/lsp/test_server.py`), and the `initialize` answer is part of
each transcript, so the reader can see the precondition it ran under.

## The corpus the ranges are measured against

A temp directory (`…/my corpus ü/corpus`, created by the `lsp_corpus` fixture),
indexed into the collection `lsp-probe`:

`sample.py` (6 lines as indexed, 10 after the diagnostics edit)

```
def alpha():
    return 1


def beta():
    return alpha()
```

`notes.md` (5 lines)

```
# Retrieval Notes

## Scoring

Penguin migration survey along the Antarctic coastline.
```

## Normalization (why the files are comparable at all)

Two things differ on every machine and carry no evidence, so they are rewritten
before comparison:

| Raw | Recorded as | Why |
|-----|-------------|-----|
| `file:///…/my%20corpus%20%C3%BC/corpus/…` | `file://<corpus>/…` | the fixture's temp path; percent-encoding is still proven, because the fixture path contains a space and a non-ASCII character and the transcript shows it surviving the round trip as a parseable URI |
| `serverInfo.version` | `<version>` | a package version bump is not a behaviour change |

Everything else — ids, methods, ranges, characters, severities, codes,
messages — is compared exactly.

## Reading the diagnostics transcript

The session is three document events, and the edit between the first two is
deliberate (the server reads the file from disk, so without it there is nothing
stale to report):

1. `didOpen` on a file indexed seconds ago → `diagnostics: []` (healthy; the
   empty array is also the clear);
2. the test appends `"\n\ndef gamma():\n    return 2\n"` to `sample.py` **with
   no reindex**, then `didSave` → exactly one `index-stale` diagnostic, severity
   3 (Information), range measured from the edited file (0,0 → 10,0 — the whole
   document, because one chunk of it is out of date);
3. `didClose` → `diagnostics: []`.

There is no type checking anywhere in these files: the diagnostic says the index
is behind the file on disk, which is a fact the index can prove.

## Refreshing

```bash
INDEXED_LSP_EVIDENCE_UPDATE=1 uv run pytest tests/system/test_lsp_out_of_process.py
```

Then read the diff. Every changed line is a change in what the editor is told,
so it belongs in the PR description, not just in a commit.
