"""route_matter — route a matter description across all four form libraries.

Deterministic path (always available): lexical token scoring over the merged
catalog (``catalog/merged_catalog.json``) plus the cross-repo workflow bundles
(``catalog/workflows.json``). Workflows act as a recall bridge: when a matter
matches a workflow, that workflow's member forms are boosted, so multi-repo
bundles surface ahead of lexically-coincidental single forms.

Optional LLM path: a single chat call over the compact catalog — the proven
sibling-router pattern (cached catalog in one prompt, no embeddings,
enum-validated answer, explicit NONE option, one retry on an empty parse).
It is used **only** when an OpenAI-compatible endpoint is configured via
environment variables; there is no built-in default endpoint:

    ROUTER_BASE_URL   (or OPENAI_BASE_URL)  e.g. https://api.example.com/v1
    ROUTER_MODEL      (or OPENAI_MODEL)     model name, default "local"
    ROUTER_API_KEY    (or OPENAI_API_KEY)   bearer token, default "none"

On any LLM failure the lexical result is returned, so route_matter always
answers. This module routes only — filling stays in the owning repo.
"""
from __future__ import annotations

import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "catalog" / "merged_catalog.json"
WORKFLOWS_PATH = ROOT / "catalog" / "workflows.json"

_STOP = {
    "the", "a", "an", "of", "for", "to", "and", "or", "with", "in", "on",
    "is", "are", "was", "be", "maine", "file", "filing",
    "client", "wants", "needs", "case", "matter", "after", "before", "about",
    "need", "want", "help", "please", "how", "what", "which",
}
# "form"/"forms" stay meaningful in queries and workflow keywords ("form an
# LLC" = formation) but are noise inside per-form haystacks (corp hints carry
# "form ASUM-5"-style text), so they are stripped only there.
_FORM_NOISE = {"form", "forms"}

# a workflow must match this many query tokens before its members get boosted
_WF_BOOST_MIN = 2

_CACHE: dict[str, dict] = {}


def _tokens(text: str) -> set[str]:
    toks = set()
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w in _STOP or len(w) <= 2:
            continue
        toks.add(w)
        # light plural fold so "estates" matches "estate"
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            toks.add(w[:-1])
    return toks


def load_catalog(path: pathlib.Path | None = None) -> dict:
    p = str(path or CATALOG_PATH)
    if p not in _CACHE:
        _CACHE[p] = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    return _CACHE[p]


def load_workflows(path: pathlib.Path | None = None) -> dict:
    p = str(path or WORKFLOWS_PATH)
    if p not in _CACHE:
        _CACHE[p] = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    return _CACHE[p]


def _form_key(f: dict) -> str:
    return f"{f['repo']}/{f['form_id']}"


def _haystack(f: dict) -> set[str]:
    return _tokens(" ".join(
        [f.get("title", ""), f.get("domain", ""), f["form_id"]]
        + list(f.get("keywords", [])))) - _FORM_NOISE


# ---------------------------------------------------------------- workflows

def _match_workflows(q: set[str], workflows: dict) -> list[tuple[int, str, dict]]:
    hits = []
    for key, w in workflows.get("workflows", {}).items():
        hay = _tokens(" ".join(
            [w.get("name", ""), w.get("description", "")]
            + list(w.get("keywords", []))))
        score = len(q & hay)
        if score:
            hits.append((score, key, w))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return hits


# ------------------------------------------------------------ lexical path

def _exact_ids(situation: str, forms: list[dict]) -> list[dict]:
    """Form-id short-circuit: a query naming a known id verbatim returns it.

    The lexical tokenizer drops short tokens, so "fill ME-RETTD" would route
    poorly without this (ported from the court repo's find_forms).
    """
    by_id: dict[str, list[dict]] = {}
    for f in forms:
        by_id.setdefault(f["form_id"].upper(), []).append(f)
    hits, seen = [], set()
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)+", situation):
        for f in by_id.get(tok.upper(), []):
            k = _form_key(f)
            if k not in seen:
                seen.add(k)
                hits.append(f)
    return hits


def _lexical(situation: str, forms: list[dict], wf_hits, top_k: int):
    q = _tokens(situation)

    # member boost from strongly-matched workflows (best one weighs the most);
    # single-token workflow grazes don't get to reorder the form ranking
    boosting = [h for h in wf_hits if h[0] >= _WF_BOOST_MIN]
    boost: dict[str, tuple[int, int]] = {}  # key -> (bonus, step_order)
    for rank, (wscore, _key, w) in enumerate(boosting[:2]):
        for order, step in enumerate(w.get("steps", [])):
            k = f"{step['repo']}/{step['form_id']}"
            weight = 2 if not step.get("optional") else 1
            bonus = weight * wscore * (2 if rank == 0 else 1)
            cur = boost.get(k)
            if cur is None or bonus > cur[0]:
                boost[k] = (bonus, order)

    scored = []
    for f in forms:
        neg = _tokens(" ".join(f.get("negative_keywords", [])))
        if neg and (q & neg):
            continue
        hay = _haystack(f)
        matched = q & hay
        base = 2 * len(matched)
        bonus, order = boost.get(_form_key(f), (0, 99))
        score = base + bonus
        if score <= 0:
            continue
        why = []
        if matched:
            why.append("matched: " + ", ".join(sorted(matched)))
        if bonus:
            why.append(f"in matched workflow (step {order + 1})")
        scored.append((-score, order, f["form_id"], f, "; ".join(why)))
    scored.sort(key=lambda s: s[:3])
    return [
        {"repo": f["repo"], "form_id": f["form_id"],
         "title": f.get("title", ""), "why": why}
        for _, _, _, f, why in scored[:top_k]
    ]


# ---------------------------------------------------------------- LLM path

def _llm_config():
    base = os.environ.get("ROUTER_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if not base:
        return None
    return {
        "base": base.rstrip("/"),
        "model": os.environ.get("ROUTER_MODEL")
        or os.environ.get("OPENAI_MODEL") or "local",
        "key": os.environ.get("ROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY") or "none",
    }


def _llm_call(cfg: dict, prompt: str) -> str:
    import urllib.request
    body = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 300,
    }).encode()
    req = urllib.request.Request(
        f"{cfg['base']}/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg['key']}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _llm(situation: str, forms: list[dict], top_k: int) -> list[dict] | None:
    """Single cached-catalog LLM call; enum-validated; NONE option; one retry."""
    cfg = _llm_config()
    if cfg is None:
        return None
    by_key = {_form_key(f): f for f in forms}
    lines = []
    for f in forms:
        kw = "; ".join(f.get("keywords", []))
        lines.append(f"{_form_key(f)} | {f.get('domain', '')} | "
                     f"{f.get('title', '')}" + (f" [{kw}]" if kw else ""))
    prompt = (
        "You route a legal/tax matter description to public Maine forms drawn "
        "from four libraries (court, probate, corporation, transactional-tax). "
        "Pick the most likely forms from the catalog below. Return ONLY a JSON "
        "array of \"repo/form_id\" strings exactly as they appear in the "
        f"catalog, best first, max {top_k}. If nothing fits, return "
        "[\"NONE\"].\n\n/no_think\n\nCATALOG:\n" + "\n".join(lines)
        + f"\n\nMATTER: {situation}\n\nJSON:"
    )
    for _attempt in range(2):  # retry-on-empty once
        text = _llm_call(cfg, prompt)
        try:
            arr = json.loads(text[text.index("["):text.rindex("]") + 1])
        except ValueError:
            continue
        if arr == ["NONE"]:
            return []
        valid = [by_key[k] for k in arr if isinstance(k, str) and k in by_key]
        if valid:
            return [
                {"repo": f["repo"], "form_id": f["form_id"],
                 "title": f.get("title", ""), "why": "llm-selected"}
                for f in valid[:top_k]
            ]
    return None  # fall back to lexical


# ------------------------------------------------------------------- entry

def route_matter(situation: str, top_k: int = 8,
                 catalog: dict | None = None,
                 workflows: dict | None = None) -> dict:
    """Route a free-text matter description to forms + cross-repo workflows.

    Returns ``{situation, mode, workflows: [...], forms: [{repo, form_id,
    title, why}]}``. ``mode`` is ``"llm"`` when an env-configured endpoint
    answered, else ``"lexical"`` (also covers the exact-id short-circuit).
    """
    cat = catalog if catalog is not None else load_catalog()
    wfs = workflows if workflows is not None else load_workflows()
    forms = cat["forms"]
    q = _tokens(situation)
    wf_hits = _match_workflows(q, wfs)

    # surface workflows only on a solid (>= _WF_BOOST_MIN tokens) match;
    # a single-token graze is not evidence the matter is that bundle
    surfaced = [h for h in wf_hits if h[0] >= _WF_BOOST_MIN]
    wf_out = [
        {"key": key, "name": w.get("name", key),
         "description": w.get("description", ""),
         "forms": [{"repo": s["repo"], "form_id": s["form_id"],
                    "role": s.get("role", ""),
                    "optional": bool(s.get("optional")),
                    "inferred": bool(s.get("inferred"))}
                   for s in w.get("steps", [])]}
        for _score, key, w in surfaced[:3]
    ]

    exact = _exact_ids(situation, forms)
    if exact:
        return {
            "situation": situation, "mode": "lexical", "workflows": wf_out,
            "forms": [{"repo": f["repo"], "form_id": f["form_id"],
                       "title": f.get("title", ""), "why": "exact form-id match"}
                      for f in exact[:top_k]],
        }

    try:
        results = _llm(situation, forms, top_k)
    except Exception:
        results = None
    mode = "llm" if results else "lexical"
    if not results:  # no endpoint configured, LLM failed, or LLM said NONE
        results = _lexical(situation, forms, wf_hits, top_k)
    return {"situation": situation, "mode": mode,
            "workflows": wf_out, "forms": results}


def main() -> int:  # python3 -m src.router "<situation>"
    import argparse
    ap = argparse.ArgumentParser(
        description="Route a matter description across the four Maine form libraries.")
    ap.add_argument("situation", help="free-text matter description")
    ap.add_argument("--top-k", type=int,
                    default=int(os.environ.get("ROUTER_TOP_K", "8")))
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()
    res = route_matter(args.situation, args.top_k)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    print(f"[{res['mode']}]")
    for w in res["workflows"]:
        forms = ", ".join(f"{s['repo'].split('-')[1]}:{s['form_id']}"
                          for s in w["forms"])
        print(f"workflow [{w['key']}] {w['name']} -> {forms}")
    for f in res["forms"]:
        print(f"  {f['repo']:26} {f['form_id']:14} {f['title'][:44]}")
    if not res["workflows"] and not res["forms"]:
        print("No matches — try different wording, or browse catalog/merged_catalog.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
