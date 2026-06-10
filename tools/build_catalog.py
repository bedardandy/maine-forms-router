#!/usr/bin/env python3
"""Build catalog/merged_catalog.json from the four sibling repos' catalogs.

Reads each repo's own catalog dialect (see src/merge.py), normalizes to one
shape, and writes:

    catalog/merged_catalog.json     the merged catalog (+ per-repo sources block)
    catalog/merged_catalog.sha256   sha256 of the JSON + per-repo source commits

Sources, two modes:

    python3 tools/build_catalog.py
        Default: fetch raw files from https://raw.githubusercontent.com/
        <org>/<repo>/main/... and record each repo's current main commit
        (via the GitHub API). Needs network.

    python3 tools/build_catalog.py --repos-dir /path/to/checkouts
        Read local checkouts named exactly like the repos; records each
        checkout's HEAD commit. No network.

Refreshing the committed snapshot is just rerunning this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.merge import (  # noqa: E402
    merge, normalize_corp, normalize_court, normalize_probate, normalize_tax,
)
from src.repos import GITHUB_ORG, REPOS  # noqa: E402

RAW_BASE = "https://raw.githubusercontent.com"
API_BASE = "https://api.github.com"


def _fetch(url: str):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def _load_remote(repo: str, path: str):
    return _fetch(f"{RAW_BASE}/{GITHUB_ORG}/{repo}/main/{path}")


def _remote_commit(repo: str) -> str | None:
    try:
        return _fetch(f"{API_BASE}/repos/{GITHUB_ORG}/{repo}/commits/main")["sha"]
    except Exception:
        return None


def _load_local(repos_dir: pathlib.Path, repo: str, path: str):
    return json.loads((repos_dir / repo / path).read_text(encoding="utf-8"))


def _local_commit(repos_dir: pathlib.Path, repo: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(repos_dir / repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def build(repos_dir: pathlib.Path | None = None) -> dict:
    if repos_dir is not None:
        def load(repo, path):
            return _load_local(repos_dir, repo, path)

        def commit(repo):
            return _local_commit(repos_dir, repo)
        fetched = "local"
    else:
        load, commit, fetched = _load_remote, _remote_commit, "remote"

    per_repo = {
        "maine-court-forms": normalize_court(
            load("maine-court-forms", "catalog/forms_index.json")),
        "maine-probate-forms": normalize_probate(
            load("maine-probate-forms", "catalog/router_catalog.json"),
            load("maine-probate-forms", "catalog/fill_geometry_status.json")),
        "maine-corporation-forms": normalize_corp(
            load("maine-corporation-forms", "catalog/forms_index.json"),
            load("maine-corporation-forms", "catalog/router_catalog.json")),
        "transactional-tax-forms": normalize_tax(
            load("transactional-tax-forms", "catalog/forms_index.json"),
            load("transactional-tax-forms", "catalog/by_domain.json")),
    }
    sources = {repo: {"commit": commit(repo), "fetched": fetched}
               for repo in per_repo}
    return merge(per_repo, sources)


def write(doc: dict, out_dir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cat_path = out_dir / "merged_catalog.json"
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    cat_path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = [f"{digest}  merged_catalog.json", "# sources"]
    for repo, src in doc["sources"].items():
        lines.append(f"# {repo} {src.get('commit') or 'unknown'}"
                     f" ({src.get('fetched')}, {src['n_forms']} forms)")
    sha_path = out_dir / "merged_catalog.sha256"
    sha_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cat_path, sha_path


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos-dir", type=pathlib.Path, default=None,
                    help="directory holding local checkouts of the four repos"
                         " (default: fetch from raw.githubusercontent.com)")
    ap.add_argument("--out-dir", type=pathlib.Path, default=ROOT / "catalog")
    args = ap.parse_args()
    doc = build(args.repos_dir)
    cat_path, sha_path = write(doc, args.out_dir)
    per = {r: s["n_forms"] for r, s in doc["sources"].items()}
    print(f"wrote {cat_path} ({doc['count']} forms: {per})")
    print(f"wrote {sha_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
