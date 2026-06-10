"""Catalog normalization (real per-repo excerpts) + committed-snapshot integrity."""
import hashlib
import json
import pathlib

import pytest

from conftest import ROOT, load_fixture
from src.merge import (
    merge, normalize_corp, normalize_court, normalize_probate, normalize_tax,
)
from src.repos import REPOS

REQUIRED_KEYS = {"repo", "form_id", "title", "domain", "status", "keywords", "path"}


# ------------------------------------------------------------- normalizers

def test_normalize_court():
    out = normalize_court(load_fixture("court_forms_index.json"))
    assert len(out) == 5
    by_id = {f["form_id"]: f for f in out}
    ad = by_id["AD-001"]
    assert REQUIRED_KEYS <= set(ad)
    assert ad["title"] == "Petition for Adoption and Change of Name"  # id prefix stripped
    assert ad["domain"] == "Adoption"
    assert ad["status"] is None  # court trust tier lives per-form, not in its catalog
    assert ad["path"] == "forms/AD-001"
    assert by_id["CV-007"]["keywords"]  # surgical keyword bridge survives
    assert by_id["BCCP-2010"].get("negative_keywords")  # disqualifier survives


def test_normalize_corp():
    out = normalize_corp(load_fixture("corp_forms_index.json"),
                         load_fixture("corp_router_catalog.json"))
    by_id = {f["form_id"]: f for f in out}
    llc = by_id["LLC_MLLC-6"]
    assert REQUIRED_KEYS <= set(llc)
    assert llc["domain"] == "Limited Liability Company"
    assert "fields mapped" in llc["status"]  # "<m>/<n> fields mapped"
    assert "MLLC-6" in " ".join(llc["keywords"])  # router hints + bare code
    assert llc["path"] == "forms/LLC_MLLC-6"


def test_normalize_tax():
    out = normalize_tax(load_fixture("tax_forms_index.json"),
                        load_fixture("tax_by_domain.json"))
    assert len(out) == 14
    by_id = {f["form_id"]: f for f in out}
    rettd = by_id["ME-RETTD"]
    assert rettd["domain"] == "real-estate"
    assert rettd["status"] == "opus-adjudicated"  # status passes through verbatim
    assert by_id["MRS-706ME"]["status"] == "mapped"


def test_normalize_tax_domain_disagreement_raises():
    idx = load_fixture("tax_forms_index.json")
    bad = json.loads(json.dumps(load_fixture("tax_by_domain.json")))
    bad["by_domain"]["corporations"]["form_ids"].append("ME-RETTD")
    with pytest.raises(ValueError, match="ME-RETTD"):
        normalize_tax(idx, bad)


def test_normalize_probate():
    out = normalize_probate(load_fixture("probate_router_catalog.json"),
                            load_fixture("probate_fill_geometry_status.json"))
    by_id = {f["form_id"]: f for f in out}
    de = by_id["DE-101"]
    assert de["title"].startswith("Application for Informal Probate")
    assert de["domain"] == "estates"
    assert de["status"] == "geometry-generated"
    assert de["path"] == "repo/forms/DE-101"
    # AF-103 carries a surgical disambiguation hint beyond its title
    assert by_id["AF-103"]["keywords"] and "AFFIDAVIT" in by_id["AF-103"]["keywords"][0]
    # AF-102 has no surgical suffix -> no hint
    assert by_id["AF-102"]["keywords"] == []


def test_merge_rejects_unknown_repo():
    with pytest.raises(ValueError):
        merge({"not-a-repo": []})


def test_merge_sources_block():
    doc = merge(
        {"transactional-tax-forms": normalize_tax(load_fixture("tax_forms_index.json"))},
        sources={"transactional-tax-forms": {"commit": "abc123", "fetched": "local"}})
    src = doc["sources"]["transactional-tax-forms"]
    assert src["commit"] == "abc123"
    assert src["n_forms"] == 14
    assert src["clone_url"].endswith("transactional-tax-forms.git")
    assert doc["count"] == 14


# ---------------------------------------------------- committed snapshot

def _snapshot():
    return json.loads((ROOT / "catalog" / "merged_catalog.json").read_text())


def test_snapshot_integrity():
    doc = _snapshot()
    assert doc["count"] == len(doc["forms"])
    assert set(doc["sources"]) == set(REPOS)
    for f in doc["forms"]:
        assert REQUIRED_KEYS <= set(f), f
        assert f["repo"] in REPOS
    per_repo = {}
    for f in doc["forms"]:
        per_repo[f["repo"]] = per_repo.get(f["repo"], 0) + 1
    for repo, n in per_repo.items():
        assert n == doc["sources"][repo]["n_forms"]
        assert n > 0
    # no duplicate (repo, form_id)
    keys = [(f["repo"], f["form_id"]) for f in doc["forms"]]
    assert len(keys) == len(set(keys))


def test_snapshot_sha256_matches():
    text = (ROOT / "catalog" / "merged_catalog.json").read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    sha_file = (ROOT / "catalog" / "merged_catalog.sha256").read_text()
    assert sha_file.splitlines()[0] == f"{digest}  merged_catalog.json"
    # sources block records one commit line per repo
    commits = [l for l in sha_file.splitlines() if l.startswith("# ") and "forms)" in l]
    assert len(commits) == len(REPOS)
