---
type: area
updated: 2026-11-23
code: [src/indexed/core, src/indexed/connectors]
---

# Indexing

| Feature | Status | Description |
|---------|--------|-------------|
| **File System** | ✅ Shipped | Index local files (.pdf, .docx, .pptx, .md, etc.) |
| **Jira Cloud** | ✅ Shipped | Index Jira Cloud issues with JQL filtering |
| **Jira Server/DC** | ✅ Shipped | Index on-premises Jira with JQL filtering |
| **Confluence Cloud** | ✅ Shipped | Index Confluence Cloud pages with CQL filtering |
| **Confluence Server/DC** | ✅ Shipped | Index on-premises Confluence with CQL filtering |
| **Outline Wiki** | ✅ Shipped | Index Outline docs + attachments (Cloud or self-hosted) |
| **Chunking** | ✅ Shipped | Split documents into searchable chunks (configurable size/overlap) |
| **Incremental Updates** | ✅ Shipped | Update collections without full re-index |
| **Local watching** | ✅ Shipped | `indexed index watch` keeps a local collection current; MCP watching is opt-in (`[mcp] watch_enabled`) for the local collections present at startup |
| **Batch Processing** | ✅ Shipped | Efficient batch embedding generation |
| **GitHub Issues/PRs/Projects** | ◑ Mostly shipped | Index issues, PR threads, and Projects v2 boards ([Feature Sequence](../concepts/feature-sequence.md) Feature 19 — chunk-hash reuse follow-up not yet planned) |
| Google Drive | 📋 Planned | Index Google Docs, Sheets, Slides |
| Notion | 📋 Planned | Index Notion pages and databases |
| Slack | 📋 Planned | Index Slack messages and threads |
