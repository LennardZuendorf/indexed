---
type: question
updated: 2026-11-22
---

# Open Technical Questions

1. **Index sharding** — handle >10M documents? Shard by source? Date range? Needs benchmarking.
2. **Embedding versioning** — model update migration? Store model version in manifest? Auto re-index?
3. **Concurrent writes** — no locking on collection updates today. File locking? Atomic swap?
4. **Query caching** — cache query embeddings? Deduplicate identical queries? Invalidation?
5. **Connector reliability** — transient API failures: retry with backoff? Circuit breaker?
6. **Multi-user server mode** — DB instead of JSON files? PostgreSQL + pgvector? SQLite?
7. **CI benchmark runner stability** — the CPU-fingerprint gate handles the
   hostname randomization (see [CI Benchmarking](../tech/ci-benchmarking/ci-benchmarking.md)); `override-label` is
   configured, a skipped cross-run comparison is advisory and cannot make the
   gate green (#297), and a fleet rotation is repairable via
   `accept_cpu_change`. **Answered, 2026-10-31:** the
   hosted fleet *does* alternate — four jobs of one PR (same code) landed on
   `AMD EPYC 9V74`, `AMD EPYC 7763` (twice) and `INTEL(R) XEON(R) PLATINUM
   8573C` within an hour, producing two green and two red verdicts from the same
   diff. So a committed cross-run baseline cannot be a stable PR gate, and
   `test_parse_large_markdown` moving +10.4 % and +33.6 % against the same
   baseline on the same CPU model rules out "just raise the tolerance". The
   implemented design measures the merge's first parent and the corresponding
   PR merge result back to back in one job, keeping the committed baseline as a
   coarse `main` drift alarm. The comparator and required-row contract are
   described in CI Benchmarking above; hosted acceptance of these repairs is
   separate from local executable verification.
