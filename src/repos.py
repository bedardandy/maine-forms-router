"""The four sibling form libraries this router federates.

Single source of truth for clone URLs, per-form paths, fill entrypoints, and
each repo's own MCP server — used by the catalog merge (tools/build_catalog.py)
and by ``get_form_pointer`` (tools/agent_server.py). This router only routes;
filling stays in the owning repo via the entrypoints recorded here.
"""
from __future__ import annotations

GITHUB_ORG = "bedardandy"

REPOS: dict[str, dict] = {
    "maine-court-forms": {
        "clone_url": f"https://github.com/{GITHUB_ORG}/maine-court-forms.git",
        "description": "Maine Judicial Branch court forms (342 forms)",
        "forms_root": "forms",
        "catalog_files": ["catalog/forms_index.json"],
        "fill_entrypoint": (
            "python3 -m engine.fill_via_mapping --form <FORM_ID> --case case.json"
            " (recipe-tier forms: python3 -m engine.fill — see forms/<FORM_ID>/SKILL.md)"
        ),
        "mcp_server": "tools/mcp_server.py",
        "mcp_name": "maine-court-forms",
    },
    "maine-probate-forms": {
        "clone_url": f"https://github.com/{GITHUB_ORG}/maine-probate-forms.git",
        "description": "Maine probate court forms (79 forms)",
        "forms_root": "repo/forms",
        "catalog_files": [
            "catalog/router_catalog.json",
            "catalog/fill_geometry_status.json",
        ],
        "fill_entrypoint": (
            "python3 tools/fill_pdf.py --form <FORM_ID> --case case.json --out out.pdf"
        ),
        "mcp_server": "tools/agent_server.py",
        "mcp_name": "maine-probate-forms",
    },
    "maine-corporation-forms": {
        "clone_url": f"https://github.com/{GITHUB_ORG}/maine-corporation-forms.git",
        "description": "Maine Secretary of State business-entity forms (156 forms)",
        "forms_root": "forms",
        "catalog_files": [
            "catalog/forms_index.json",
            "catalog/router_catalog.json",
        ],
        "fill_entrypoint": "python3 -m engine.fill <FORM_ID> case.json out.pdf",
        "mcp_server": "tools/agent_server.py",
        "mcp_name": "maine-corporation-forms",
    },
    "transactional-tax-forms": {
        "clone_url": f"https://github.com/{GITHUB_ORG}/transactional-tax-forms.git",
        "description": "Maine Revenue Services + IRS transactional tax forms (14 forms)",
        "forms_root": "forms",
        "catalog_files": [
            "catalog/forms_index.json",
            "catalog/by_domain.json",
        ],
        "fill_entrypoint": (
            "python3 -m engine.fill_via_mapping --form <FORM_ID> --case case.json --out out/"
        ),
        "mcp_server": "tools/agent_server.py",
        "mcp_name": "transactional-tax-forms",
    },
}
