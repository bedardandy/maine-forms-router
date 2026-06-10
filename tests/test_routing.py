"""Lexical routing sanity over the committed merged-catalog snapshot.

No network: the catalog snapshot is committed and the LLM path is inert when
no endpoint env var is set (enforced below).
"""
import conftest  # noqa: F401  (sys.path)
import pytest

from src.router import _llm_config, route_matter


@pytest.fixture(autouse=True)
def no_llm_env(monkeypatch):
    for var in ("ROUTER_BASE_URL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


def _ids(res, n=None):
    return [(f["repo"], f["form_id"]) for f in res["forms"][:n]]


def test_no_endpoint_means_lexical_mode():
    assert _llm_config() is None
    assert route_matter("open an estate")["mode"] == "lexical"


def test_re_closing_routes_to_rettd():
    res = route_matter("transfer deed after closing")
    assert res["workflows"] and res["workflows"][0]["key"] == "re_purchase_closing"
    assert ("transactional-tax-forms", "ME-RETTD") in _ids(res, 3)


def test_llc_formation_routes_to_mllc6():
    res = route_matter("form an LLC in Maine")
    assert res["workflows"][0]["key"] == "corp_formation"
    assert _ids(res, 1) == [("maine-corporation-forms", "LLC_MLLC-6")]


def test_open_estate_routes_to_probate():
    res = route_matter("open an estate for my late father")
    assert res["workflows"][0]["key"] == "probate_estate_administration"
    top3 = _ids(res, 3)
    assert ("maine-probate-forms", "DE-101") in top3
    assert ("maine-probate-forms", "DE-201") in top3


def test_eviction_routes_to_court_without_workflow_noise():
    res = route_matter("eviction of a tenant for nonpayment of rent")
    assert res["forms"][0]["repo"] == "maine-court-forms"
    # not a known multi-repo bundle -> no workflow surfaced
    assert res["workflows"] == []


def test_dissolution_routes_to_corp():
    res = route_matter("dissolve our Maine corporation")
    assert res["workflows"][0]["key"] == "corp_dissolution"
    top = _ids(res, 5)
    assert ("maine-corporation-forms", "CORP_MBCA-11") in top


def test_exact_form_id_short_circuit():
    res = route_matter("fill ME-RETTD for the closing")
    assert _ids(res, 1) == [("transactional-tax-forms", "ME-RETTD")]
    assert res["forms"][0]["why"] == "exact form-id match"


def test_exact_form_id_collision_returns_both_owners():
    res = route_matter("AD-007")
    repos = {f["repo"] for f in res["forms"]}
    assert repos == {"maine-court-forms", "maine-probate-forms"}


def test_gibberish_returns_empty_not_crash():
    res = route_matter("zzzz qqqq xxxxx")
    assert res["forms"] == []
    assert res["workflows"] == []


def test_result_shape():
    res = route_matter("open an estate", top_k=4)
    assert set(res) == {"situation", "mode", "workflows", "forms"}
    assert len(res["forms"]) <= 4
    for f in res["forms"]:
        assert set(f) == {"repo", "form_id", "title", "why"}
    for w in res["workflows"]:
        assert {"key", "name", "description", "forms"} <= set(w)
        for s in w["forms"]:
            assert {"repo", "form_id", "role", "optional", "inferred"} <= set(s)
