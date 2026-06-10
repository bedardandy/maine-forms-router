"""Normalize the four sibling repos' catalogs into one merged shape.

Each repo publishes a different catalog dialect (see the source repos):

- maine-court-forms:        catalog/forms_index.json — bare list, key ``form``
- maine-corporation-forms:  catalog/forms_index.json ``{"forms": [...]}`` +
                            catalog/router_catalog.json (per-form hints)
- transactional-tax-forms:  catalog/forms_index.json ``{"count", "forms"}``
- maine-probate-forms:      catalog/router_catalog.json (pipe-delimited
                            ``cat_title`` / ``cat_surgical`` text catalogs) +
                            catalog/fill_geometry_status.json

This module flattens all four to one entry shape::

    {repo, form_id, title, domain, status, keywords, path}

plus optional ``negative_keywords`` (court carries a few). ``status`` is the
repo-native trust signal where the repo publishes one in its catalog:

- tax:     ``mapped`` / ``opus-adjudicated`` / ``remap-pending`` / ``unmapped``
- corp:    ``"<mapped>/<total> fields mapped"``
- probate: ``geometry-generated`` / ``plan-only``
- court:   ``None`` — court's trust tier lives per-form in
           ``forms/<ID>/mapping.json`` (``recipe``/``verified``/...), not in
           its catalog; ask the owning repo.
"""
from __future__ import annotations

from .repos import REPOS

EM_DASH = "—"


def _as_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def normalize_court(forms_index: list[dict]) -> list[dict]:
    """maine-court-forms catalog/forms_index.json (bare list, key ``form``)."""
    out = []
    for f in forms_index:
        form_id = f["form"]
        title = f.get("title", form_id)
        # Titles repeat the id ("AD-001 — Petition ..."); keep the prose half.
        if f" {EM_DASH} " in title:
            title = title.split(f" {EM_DASH} ", 1)[1]
        entry = {
            "repo": "maine-court-forms",
            "form_id": form_id,
            "title": title,
            "domain": f.get("category", ""),
            "status": None,
            "keywords": _as_list(f.get("keywords")),
            "path": f"forms/{form_id}",
        }
        neg = _as_list(f.get("negative_keywords"))
        if neg:
            entry["negative_keywords"] = neg
        out.append(entry)
    return out


def normalize_corp(forms_index: dict, router_catalog: dict) -> list[dict]:
    """maine-corporation-forms forms_index.json + router_catalog.json hints."""
    hints = {f["form_id"]: f.get("hints", [])
             for f in router_catalog.get("forms", [])}
    out = []
    for f in forms_index["forms"]:
        mapped = f.get("mapped_fields")
        total = f.get("num_fields")
        status = (f"{mapped}/{total} fields mapped"
                  if mapped is not None and total is not None else None)
        out.append({
            "repo": "maine-corporation-forms",
            "form_id": f["form_id"],
            "title": f.get("title", f["form_id"]),
            "domain": f.get("entity_type", ""),
            "status": status,
            "keywords": _as_list(hints.get(f["form_id"]))
            + _as_list(f.get("code")),
            "path": f.get("path", f"forms/{f['form_id']}"),
        })
    return out


def normalize_tax(forms_index: dict, by_domain: dict | None = None) -> list[dict]:
    """transactional-tax-forms forms_index.json (+ by_domain cross-check)."""
    domains_of: dict[str, set[str]] = {}
    if by_domain:
        for dom, blk in by_domain.get("by_domain", {}).items():
            for fid in blk.get("form_ids", []):
                domains_of.setdefault(fid, set()).add(dom)
    out = []
    for f in forms_index["forms"]:
        fid = f["form_id"]
        dom = f.get("domain", "")
        if fid in domains_of and domains_of[fid] != {dom}:
            raise ValueError(
                f"tax catalog disagreement for {fid}: forms_index says {dom!r},"
                f" by_domain says {sorted(domains_of[fid])}")
        out.append({
            "repo": "transactional-tax-forms",
            "form_id": fid,
            "title": f.get("title", fid),
            "domain": dom,
            "status": f.get("status"),
            "keywords": _as_list(f.get("agency")),
            "path": f"forms/{fid}",
        })
    return out


def normalize_probate(router_catalog: dict,
                      geometry_status: dict | None = None) -> list[dict]:
    """maine-probate-forms catalog/router_catalog.json.

    ``cat_title`` lines are ``ID | category | Title``; ``cat_surgical`` repeats
    them with an optional `` — disambiguation hint`` suffix on the forms the
    surgical pass enriched.
    """
    titles: dict[str, tuple[str, str]] = {}
    for line in router_catalog["cat_title"].splitlines():
        if not line.strip():
            continue
        fid, cat, title = (p.strip() for p in line.split("|", 2))
        titles[fid] = (cat, title)

    hints: dict[str, str] = {}
    for line in router_catalog.get("cat_surgical", "").splitlines():
        if not line.strip():
            continue
        fid, _cat, rest = (p.strip() for p in line.split("|", 2))
        title = titles.get(fid, ("", ""))[1]
        if title and rest.startswith(title) and len(rest) > len(title):
            hints[fid] = rest[len(title):].strip(f" {EM_DASH}-")

    generated = set((geometry_status or {}).get("generated", []))
    plan_only = set((geometry_status or {}).get("plan_only", []))

    out = []
    for fid in router_catalog["form_ids"]:
        cat, title = titles.get(fid, ("", fid))
        status = ("geometry-generated" if fid in generated
                  else "plan-only" if fid in plan_only else None)
        out.append({
            "repo": "maine-probate-forms",
            "form_id": fid,
            "title": title,
            "domain": cat,
            "status": status,
            "keywords": [hints[fid]] if fid in hints else [],
            "path": f"repo/forms/{fid}",
        })
    return out


def merge(per_repo: dict[str, list[dict]],
          sources: dict[str, dict] | None = None) -> dict:
    """Assemble the merged catalog document from per-repo normalized lists."""
    unknown = set(per_repo) - set(REPOS)
    if unknown:
        raise ValueError(f"unknown repos: {sorted(unknown)}")
    forms = []
    for repo in sorted(per_repo):
        forms.extend(sorted(per_repo[repo], key=lambda f: f["form_id"]))
    src = {}
    for repo in sorted(per_repo):
        src[repo] = {
            "clone_url": REPOS[repo]["clone_url"],
            "files": REPOS[repo]["catalog_files"],
            "n_forms": len(per_repo[repo]),
            **(sources or {}).get(repo, {}),
        }
    return {
        "generated_by": "tools/build_catalog.py",
        "sources": src,
        "count": len(forms),
        "forms": forms,
    }
