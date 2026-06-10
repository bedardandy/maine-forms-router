# maine-forms-router

Umbrella router for multi-repo legal matters across the four public Maine form
libraries. One question, one entry point: **given a matter, which forms — from
which repo?**

Real matters cross repos. A Maine real-estate closing needs the tax repo's
ME-RETTD alongside any court/probate companions; administering an estate needs
probate filings *and* MRS-706ME / IRS-1041; forming an LLC needs the Secretary
of State filing *and* IRS-SS-4. Each sibling repo routes well inside its own
catalog; none can see the others. This repo merges the four catalogs and routes
across them — and **only routes**: filling (and its trust tiers, fill
verification, drift guards) stays in the owning repo.

> **Not legal or tax advice.** Routing output is a suggestion that a qualified
> professional must verify. See [`DISCLAIMER.md`](DISCLAIMER.md).

## The four libraries

| Repo | Covers | Forms |
|---|---|---|
| [maine-court-forms](https://github.com/bedardandy/maine-court-forms) | Maine Judicial Branch court forms | 342 |
| [maine-probate-forms](https://github.com/bedardandy/maine-probate-forms) | Maine probate court forms | 79 |
| [maine-corporation-forms](https://github.com/bedardandy/maine-corporation-forms) | Maine SoS business-entity forms | 156 |
| [transactional-tax-forms](https://github.com/bedardandy/transactional-tax-forms) | MRS + IRS transactional tax forms | 14 |

## What's here

- **`catalog/merged_catalog.json`** — the four repos' catalogs (each its own
  dialect) normalized to one shape:
  `{repo, form_id, title, domain, status, keywords, path}`, with a per-repo
  `sources` block recording the source commit. 591 forms.
  `merged_catalog.sha256` pins the snapshot.
- **`catalog/workflows.json`** — the known cross-repo bundles: real-estate
  purchase/closing, probate estate administration, entity formation, entity
  dissolution. Every member form is validated against the merged catalog in CI;
  members marked `"inferred": true` are this project's inference, not the
  owning repo's statement.
- **`src/router.py`** — `route_matter(situation, top_k)`: deterministic lexical
  routing (the siblings' proven no-embeddings pattern), workflow matching with
  member boosting, exact form-id short-circuit, and an optional single-call LLM
  path (enum-validated, NONE option, retry-on-empty) used only when an endpoint
  is configured via env.
- **`tools/agent_server.py`** — MCP server: `route_matter`, `list_workflows`,
  `get_form_pointer`.
- **`tools/build_catalog.py`** — rebuilds the merged catalog from the four
  repos (GitHub `main` by default, `--repos-dir` for local checkouts).

## Install

```bash
git clone https://github.com/bedardandy/maine-forms-router.git
cd maine-forms-router
pip install -r requirements.txt   # only needed for the MCP server
```

Route from the CLI (stdlib-only, no network):

```bash
python3 -m src.router "open an estate for my late father"
python3 -m src.router --json "transfer deed after closing"
```

## MCP registration

```bash
claude mcp add maine-forms-router -- python3 tools/agent_server.py
```

Tools:

- `route_matter(situation, top_k=8)` → ranked `[{repo, form_id, title, why}]`
  plus matching cross-repo workflows.
- `list_workflows()` → the workflow bundles with each member's repo, role,
  `optional` / `inferred` flags, and pick-one `alternative_group`s.
- `get_form_pointer(form_id, repo="")` → which repo owns the form: clone URL,
  per-form path, that repo's fill entrypoint and its own MCP server, so a
  harness can chain into the owning repo. Pass `repo=` for the few ids that
  exist in both court and probate (e.g. `AD-007`).

The four sibling MCP servers have unique names, so registering all five at
once works; this router is the entry point, the siblings do the filling.

## Optional LLM routing

The router is fully functional without any LLM. To enable the single-call LLM
path, point it at any OpenAI-compatible endpoint via environment variables
(there is no built-in default):

```bash
export ROUTER_BASE_URL=https://api.example.com/v1   # or OPENAI_BASE_URL
export ROUTER_MODEL=<model-name>                    # or OPENAI_MODEL
export ROUTER_API_KEY=<key>                         # or OPENAI_API_KEY
```

Invalid or empty LLM answers fall back to the lexical path automatically.

## Refreshing the catalog

The merged catalog is a committed snapshot; refreshing it is rerunning the
tool and committing the result:

```bash
python3 tools/build_catalog.py                      # fetch from GitHub main
python3 tools/build_catalog.py --repos-dir ~/src    # or from local checkouts
python3 -m pytest tests/                            # workflow ids must still exist
```

## Tests

```bash
python -m pytest tests/ -v
```

Network-free: catalog normalization against real per-repo catalog excerpts,
routing sanity, workflow-membership validation against the merged catalog, and
MCP tool shapes.

## License

Apache-2.0 (see [`LICENSE`](LICENSE)). Not affiliated with any court or agency;
form names/numbers identify the public forms they describe.
