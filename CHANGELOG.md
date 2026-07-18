# Changelog

## 0.1.1 — 2026-07-18

- Include bounded inline source excerpts for readable application and dependency
  traceback frames so
  Errorgap can render highlighted source without a repository integration.
- Order traceback frames innermost-first so frame 0 and group fingerprints use
  the actual exception site.
