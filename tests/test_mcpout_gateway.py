# SPDX-License-Identifier: LicenseRef-Mcpout
"""Mcpout-Gateway ohne Netz: Lesen/Schreiben getrennt, Vorschau vor confirm, Batch stoppt, Löschen gesperrt, Methoden-Freigabe."""
import json

import pytest

from mcp_server_odoo import mcpout_gateway as G


class FakeConn:
    uid = 6

    def __init__(self):
        self.calls = []

    def execute_kw(self, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        if method == "search_read":
            return [{"id": 1, "name": "A", "partner_id": [3, "Kunde"]}, {"id": 2, "name": "B", "partner_id": False}]
        if method == "create":
            return 99 if isinstance(args[0], dict) else [99, 100]
        if method == "write":
            return True
        if method == "search_count":
            return 7
        if method == "read_group":
            return [{"state": "sale", "__count": 3}]
        if method == "load":
            return {"ids": [5], "messages": []}
        if method == "fail":
            raise RuntimeError("boom")
        return True


@pytest.fixture
def o(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "DATA", tmp_path)
    return G.Odoo(FakeConn())


def test_find_lists_all_ops_with_kind():
    ops = {x["operation"]: x["kind"] for x in G.find()}
    assert ops["search"] == "read" and ops["create"] == "write" and ops["payment_register"] == "write"
    assert {"export", "import", "message_post", "attach", "create_many", "aggregate"} <= set(ops)
    assert [x["operation"] for x in G.find("chatter")] == ["message_post"]


def test_read_runs_and_refuses_writes(o):
    assert G.run_read(o, "count", {"model": "sale.order"}) == 7
    assert G.run_read(o, "search", {"model": "res.partner", "limit": 9999})[0]["name"] == "A"
    assert o.conn.calls[-1][3]["limit"] == G.MAX_ROWS
    with pytest.raises(PermissionError):
        G.run_read(o, "create", {"model": "res.partner", "values": {"name": "X"}})
    with pytest.raises(ValueError):
        G.run_read(o, "gibtsnicht", {})


def test_export_csv(o):
    r = G.run_read(o, "export", {"model": "sale.order", "fields": ["name", "partner_id"]})
    assert r["rows"] == 2 and "A;Kunde" in r["csv"] and r["csv"].splitlines()[2] == "B;"


def test_write_preview_then_confirm_and_audit(o, tmp_path):
    r = G.run_write(o, "update", {"model": "res.partner", "ids": [7], "values": {"phone": "1"}}, confirm=False)
    assert "preview" in r and not any(c[1] == "write" for c in o.conn.calls)
    r = G.run_write(o, "update", {"model": "res.partner", "ids": [7], "values": {"phone": "1"}}, confirm=True)
    assert r["ok"] and o.conn.calls[-1][1] == "write"
    line = json.loads((tmp_path / "mcpout_audit.jsonl").read_text().splitlines()[-1])
    assert line["op"] == "update" and line["model"] == "res.partner"


def test_import_needs_external_id(o):
    with pytest.raises(ValueError):
        G.run_write(o, "import", {"model": "res.partner", "fields": ["name"], "rows": [["X"]]}, confirm=True)
    assert G.run_write(o, "import", {"model": "res.partner", "fields": ["id", "name"], "rows": [["__import__.k1", "X"]]}, confirm=True)["result"]["ids"] == [5]


def test_delete_locked_and_methods_allowlisted(o, monkeypatch):
    with pytest.raises(PermissionError):
        G.run_write(o, "delete", {"model": "res.partner", "ids": [1]}, confirm=True)
    with pytest.raises(PermissionError):
        G.run_write(o, "call", {"model": "res.partner", "method": "unlink", "ids": [1]}, confirm=True)
    assert G.run_write(o, "call", {"model": "sale.order", "method": "action_confirm", "ids": [1]}, confirm=True)["ok"]
    monkeypatch.setenv("MCPOUT_ALLOW_DELETE", "1")
    assert G.run_write(o, "delete", {"model": "res.partner", "ids": [1]}, confirm=True)["ok"]


def test_batch_stops_at_first_error(o):
    steps = [{"operation": "create", "params": {"model": "res.partner", "values": {"name": "A"}}},
             {"operation": "call", "params": {"model": "x", "method": "evil", "ids": [1]}},
             {"operation": "create", "params": {"model": "res.partner", "values": {"name": "B"}}}]
    r = G.run_batch(o, steps, confirm=True)
    assert r["ok"] is False and r["stopped_at"] == 2 and len(r["steps"]) == 2
    assert sum(1 for c in o.conn.calls if c[1] == "create") == 1
    assert G.run_batch(o, steps[:1], confirm=False)["steps"][0]["preview"].startswith("res.partner")


def test_payment_wizard_context(o):
    G.run_write(o, "payment_register", {"invoice_ids": [9], "amount": 10}, confirm=True)
    model, method, args, kw = o.conn.calls[-2]
    assert (model, method) == ("account.payment.register", "create") and kw["context"]["active_ids"] == [9]
    assert o.conn.calls[-1][1] == "action_create_payments"


def test_server_requires_long_secret(monkeypatch):
    monkeypatch.delenv("MCPOUT_SECRET", raising=False)
    monkeypatch.delenv("JARVIS_MCP_SECRET_ODOO", raising=False)
    with pytest.raises(RuntimeError):
        G.build_server(lambda: None)
    monkeypatch.setenv("MCPOUT_SECRET", "x" * 32)
    srv = G.build_server(lambda: None)
    assert srv.settings.streamable_http_path == "/" + "x" * 32 + "/mcp"


def test_odoo_json_formats():
    assert G._from_json({"url": "https://x", "db": "d", "user": "u", "api_key": "k"})["key"] == "k"
    assert G._from_json({"odoo": {"URL": "https://x", "DATABASE": "d", "LOGIN": "u", "PASSWORD": "p"}})["user"] == "u"
    assert G._from_json({"ODOO_URL": "https://x", "ODOO_DB": "d", "ODOO_USER": "u", "ODOO_API_KEY": "k"})["db"] == "d"
    with pytest.raises(RuntimeError):
        G._from_json({"url": "https://x"})
