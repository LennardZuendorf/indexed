---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# Logging Strategy

`loguru`, three verbosity levels:

1. **Default (quiet)** — warnings + errors only; stdout reserved for command results
2. **Verbose (`--verbose`)** — INFO; progress steps
3. **Debug (`--log-level=DEBUG`)** — internal detail, timings, HTTP requests

Log records never touch stdout. The CLI wires `bootstrap_logging` to a
stderr-backed Rich console (`cli/utils/console.py::log_console`), while
human-facing output and progress displays keep the stdout `console`. Under
`--simple-output` / `--json`, normal command returns write only the JSON body to
stdout. A CLI consumer must check exit status before parsing: an escaping error
uses the stdout console for a non-JSON Rich panel (see the failure contract below).
