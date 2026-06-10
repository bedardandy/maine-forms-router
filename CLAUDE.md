# Maine Forms Router — agent guide (AGENTS.md; same as CLAUDE.md)

The umbrella router over the four sibling Maine form libraries
([maine-court-forms](https://github.com/bedardandy/maine-court-forms),
[maine-probate-forms](https://github.com/bedardandy/maine-probate-forms),
[maine-corporation-forms](https://github.com/bedardandy/maine-corporation-forms),
[transactional-tax-forms](https://github.com/bedardandy/transactional-tax-forms)).
It answers one question: **given a matter, which forms — from which repo?**
Real matters cross repos: a real-estate closing needs the tax repo's ME-RETTD;
a probate estate needs probate filings plus MRS-706ME/IRS-1041; a new LLC needs
the SoS filing plus IRS-SS-4.

**This repo routes only — it never fills.** Filling, mapping trust tiers, fill
verification, and drift guards live in the owning repo. Chain into it via
`get_form_pointer`.

When the user describes a matter:

1. **Route:** `python3 -m src.router "<situation>"` (add `--json` for
   machine-readable) — or the MCP tool. Returns ranked `{repo, form_id, title,
   why}` candidates plus any matching **cross-repo workflow bundle**
   (`catalog/workflows.json`).
2. **Trust the workflow over single hits** when one matches — it is the curated
   multi-repo bundle. Steps marked `"inferred": true` are this project's own
   inference; verify them. `alternative_group` steps are pick-one
   (testate/intestate, LLC/corp/nonprofit).
3. **Resolve ownership:** `get_form_pointer(form_id[, repo])` → clone URL,
   per-form path, the owning repo's fill entrypoint and its own MCP server.
   Some ids collide across court/probate (e.g. AD-007) — pass `repo=`.
4. **Hand off:** clone/register the owning repo and follow **its** AGENTS.md to
   fill. Surface its `status`/trust tier; court's tier is per-form in
   `forms/<ID>/mapping.json`, not in this catalog.

**MCP server** (preferred): `python3 tools/agent_server.py` exposes
`route_matter` / `list_workflows` / `get_form_pointer` — register with
`claude mcp add maine-forms-router -- python3 tools/agent_server.py`.

## Rules
- **Not legal or tax advice.** Routing output is a suggestion; a qualified
  professional must verify form choice. Always say so. See `DISCLAIMER.md`.
- **Routing is deterministic by default** (lexical over
  `catalog/merged_catalog.json`). The optional LLM path activates only when
  `ROUTER_BASE_URL` (or `OPENAI_BASE_URL`) points at an OpenAI-compatible
  endpoint; never hardcode endpoints.
- **Never invent form ids.** Everything you cite must exist in
  `catalog/merged_catalog.json`; workflow membership is CI-gated against it.
- **Refreshing the catalog** = rerun `python3 tools/build_catalog.py`
  (fetches the four repos' catalogs from GitHub `main`; `--repos-dir` for
  local checkouts), commit the regenerated
  `catalog/merged_catalog.json` + `.sha256`.
- Licensed Apache-2.0 (`LICENSE`).
