# Mcpout Odoo (Fork-Erweiterung)

Eigene Datei `mcp_server_odoo/mcpout_gateway.py` (nicht von MPL-Dateien abgeleitet): **4 Tools statt 55** —
`odoo_find_operations` (lesen), `odoo_read` (lesen, läuft frei), `odoo_write` (ändert; ohne `confirm=true` nur Vorschau),
`odoo_write_batch` (mehrere Schritte, stoppt beim ersten Fehler). Tools tragen `readOnlyHint`/`destructiveHint`, damit
Claude/ChatGPT vor Änderungen nachfragen.

Operationen: server_info, models, fields, search, get, count, aggregate, export (CSV) · create, create_many, update,
import (externe IDs, wiederholbar), message_post, attach, payment_register, call (nur freigegebene Methoden,
`MCPOUT_ALLOWED_METHODS`), delete (nur mit `MCPOUT_ALLOW_DELETE=1`). Jede Schreibung → `$JARVIS_DATA/mcpout_audit.jsonl`.

Start: `mcpout-odoo` (streamable-HTTP, Port `MCPOUT_PORT`=8001, Pfad `/<MCPOUT_SECRET>/mcp`, Zugang `ODOO_URL/ODOO_DB/ODOO_USER/ODOO_API_KEY`
oder `$JARVIS_DATA/odoo.json`). Drop-in für den Container `jarvis-odoo` (gleicher Port, `JARVIS_MCP_SECRET_ODOO` wird akzeptiert).

Tests: `pytest tests/test_mcpout_gateway.py` (ohne Netz). Live-Lesetest 04.11.2026 gegen Odoo 16: grün.
