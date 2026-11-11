# Code navigation

Graphify is an optional development tool for tracing relationships between code files.
When it is available, build a local index with `GRAPHIFY_BACKEND=none graphify extract . --code-only`
and use `graphify query`, `graphify path`, or `graphify explain` to investigate cross-file flows.
Check results against the source; use normal file and text search for unsupported files or missing results.
The generated `graphify-out/` directory is local development output and is excluded from Git and the production image.
