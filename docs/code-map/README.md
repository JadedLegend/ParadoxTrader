# Code map

A map of the whole system, for builders arriving here.

- **`index.html`**: open it in a browser (it is self-contained and needs no server). You can pan and zoom the graph, click a part to see its purpose, design decisions, files and connections, step through three flows (a wake, a call, the owner changing settings), and read the reference tables and scan notes.
- **`data.json`**: the same map as plain data. Agents can read this instead of the HTML. Each of the 28 parts cites real `file:line` locations.

Last refreshed from `main` at `f05e15b` (2026-11-26).

## Refreshing it

Refresh it when a part is added, replaced or rewired, or when the citations drift.

1. Edit `data.json`. Every part needs real citations. Line numbers move as code changes, so re-check them.
2. Regenerate `index.html` with the code-map generator (the Claude Code `code-map` plugin: `/code-map:code-map`, or its `scripts/generate.mjs data.json index.html`). Never edit `index.html` by hand.
3. Check that every cited file exists and that each `:line` lands on the definition it names.
4. Update the "Last refreshed" line above.
