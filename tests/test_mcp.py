"""MCP tool shapes: the underlying functions, and the FastMCP registration."""
import importlib.util

import pytest

from conftest import ROOT

spec = importlib.util.spec_from_file_location(
    "agent_server", ROOT / "tools" / "agent_server.py")
agent_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_server)


def test_get_form_pointer_shape():
    p = agent_server.get_form_pointer("ME-RETTD")
    assert p["ok"] is True
    assert p["repo"] == "transactional-tax-forms"
    assert p["clone_url"] == "https://github.com/bedardandy/transactional-tax-forms.git"
    assert p["form_path"] == "forms/ME-RETTD"
    assert "engine.fill_via_mapping" in p["fill_entrypoint"]
    assert p["mcp_register"].startswith("claude mcp add transactional-tax-forms")
    assert "does not fill" in p["note"]


def test_get_form_pointer_probate_path_dialect():
    p = agent_server.get_form_pointer("DE-101")
    assert p["repo"] == "maine-probate-forms"
    assert p["form_path"] == "repo/forms/DE-101"  # probate nests under repo/
    assert "tools/fill_pdf.py" in p["fill_entrypoint"]


def test_get_form_pointer_collision_requires_repo():
    # AD-007 exists in both court and probate
    p = agent_server.get_form_pointer("AD-007")
    assert p["ok"] is False and "multiple repos" in p["error"]
    assert {c["repo"] for c in p["candidates"]} == {
        "maine-court-forms", "maine-probate-forms"}
    resolved = agent_server.get_form_pointer("AD-007", repo="maine-probate-forms")
    assert resolved["ok"] is True
    assert resolved["form_path"] == "repo/forms/AD-007"


def test_get_form_pointer_unknown_form():
    p = agent_server.get_form_pointer("NOPE-999")
    assert p["ok"] is False and "unknown form" in p["error"]


def test_list_workflows_shape():
    wfs = agent_server.list_workflows()
    assert {w["key"] for w in wfs} == {
        "re_purchase_closing", "probate_estate_administration",
        "corp_formation", "corp_dissolution"}
    for w in wfs:
        assert w["name"] and w["description"]
        for s in w["forms"]:
            assert {"repo", "form_id", "role", "optional", "inferred"} <= set(s)


def test_fastmcp_tool_registration():
    pytest.importorskip("mcp")
    import asyncio
    server = agent_server._build()
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {
        "route_matter", "list_workflows", "get_form_pointer"}
