#!/usr/bin/env python3
"""MCP server exposing the umbrella router for the four Maine form libraries.

Tools (stdio, FastMCP):
  route_matter(situation, top_k=8)   -> ranked cross-repo candidates
                                        [{repo, form_id, title, why}] plus any
                                        matching multi-repo workflow bundles
  list_workflows()                   -> the known cross-repo workflow bundles
  get_form_pointer(form_id, repo="") -> which repo owns the form: clone URL,
                                        per-form path, fill entrypoint, and
                                        that repo's own MCP server — so a
                                        harness can chain into the owning repo

This server ROUTES ONLY. It does not proxy fills: filling (and its mapping
trust tiers, fill verification, drift guards) stays in the owning repo via the
entrypoints get_form_pointer returns.

Run:      python3 tools/agent_server.py
Register: claude mcp add maine-forms-router -- python3 tools/agent_server.py

Requires ``mcp`` (pip install mcp). The import is lazy so the module documents
itself — and the underlying functions stay testable — without the dependency.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.repos import REPOS  # noqa: E402
from src.router import load_catalog, load_workflows, route_matter  # noqa: E402


def _pointer(entry: dict) -> dict:
    repo = entry["repo"]
    info = REPOS[repo]
    return {
        "ok": True,
        "repo": repo,
        "form_id": entry["form_id"],
        "title": entry.get("title", ""),
        "domain": entry.get("domain", ""),
        "status": entry.get("status"),
        "clone_url": info["clone_url"],
        "form_path": entry["path"],
        "fill_entrypoint": info["fill_entrypoint"],
        "mcp_server": info["mcp_server"],
        "mcp_register": (
            f"claude mcp add {info['mcp_name']} -- python3 {info['mcp_server']}"),
        "note": ("Run the fill from a checkout of this repo; this router does"
                 " not fill. Check the owning repo's own trust/status signals"
                 " before relying on output."),
    }


def get_form_pointer(form_id: str, repo: str = "") -> dict:
    """Resolve which repo owns ``form_id`` (ids collide across court/probate)."""
    cat = load_catalog()
    matches = [f for f in cat["forms"]
               if f["form_id"].upper() == form_id.upper()
               and (not repo or f["repo"] == repo)]
    if not matches:
        hint = f" in repo {repo!r}" if repo else ""
        return {"ok": False,
                "error": f"unknown form {form_id!r}{hint} — try route_matter"}
    if len(matches) > 1:
        return {"ok": False,
                "error": f"form id {form_id!r} exists in multiple repos;"
                         " pass repo=",
                "candidates": [{"repo": f["repo"], "form_id": f["form_id"],
                                "title": f.get("title", ""),
                                "domain": f.get("domain", "")}
                               for f in matches]}
    return _pointer(matches[0])


def list_workflows() -> list:
    """The known cross-repo workflow bundles (see catalog/workflows.json)."""
    out = []
    for key, w in load_workflows().get("workflows", {}).items():
        out.append({
            "key": key,
            "name": w.get("name", key),
            "description": w.get("description", ""),
            "forms": [{"repo": s["repo"], "form_id": s["form_id"],
                       "role": s.get("role", ""),
                       "optional": bool(s.get("optional")),
                       "inferred": bool(s.get("inferred")),
                       **({"alternative_group": s["alternative_group"]}
                          if "alternative_group" in s else {})}
                      for s in w.get("steps", [])],
        })
    return out


def _build():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("maine-forms-router")

    @mcp.tool(name="route_matter")
    def _route_matter(situation: str, top_k: int = 8) -> dict:
        """Route a free-text legal/tax matter description to candidate forms
        across all four Maine form libraries (court, probate, corporation,
        transactional-tax) plus any matching cross-repo workflow bundle.
        Routing only — fill in the owning repo (see get_form_pointer)."""
        return route_matter(situation, top_k)

    @mcp.tool(name="list_workflows")
    def _list_workflows() -> list:
        """List the known cross-repo workflow bundles (real-estate closing,
        probate estate administration, entity formation/dissolution) with each
        member form's repo, role, and whether membership is inferred."""
        return list_workflows()

    @mcp.tool(name="get_form_pointer")
    def _get_form_pointer(form_id: str, repo: str = "") -> dict:
        """Resolve which sibling repo owns a form: clone URL, per-form path,
        fill entrypoint, and that repo's own MCP server. Pass repo= when the
        id exists in more than one repo (some court/probate ids collide)."""
        return get_form_pointer(form_id, repo)

    return mcp


def main() -> int:
    try:
        mcp = _build()
    except ImportError:
        print("mcp not installed: pip install mcp", file=sys.stderr)
        return 1
    mcp.run()  # stdio transport
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
