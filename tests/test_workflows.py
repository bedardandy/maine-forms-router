"""Every workflow member must exist in the merged catalog — no fabricated forms."""
import json

from conftest import ROOT
from src.repos import REPOS


def _load():
    wf = json.loads((ROOT / "catalog" / "workflows.json").read_text())["workflows"]
    cat = json.loads((ROOT / "catalog" / "merged_catalog.json").read_text())
    return wf, {(f["repo"], f["form_id"]) for f in cat["forms"]}


def test_expected_workflows_shipped():
    wf, _ = _load()
    assert set(wf) == {"re_purchase_closing", "probate_estate_administration",
                       "corp_formation", "corp_dissolution"}


def test_every_workflow_form_exists_in_merged_catalog():
    wf, cat_keys = _load()
    missing = [(key, s["repo"], s["form_id"])
               for key, w in wf.items() for s in w["steps"]
               if (s["repo"], s["form_id"]) not in cat_keys]
    assert missing == [], f"workflow forms not in merged catalog: {missing}"


def test_workflow_step_shape():
    wf, _ = _load()
    for key, w in wf.items():
        assert w.get("name") and w.get("description") and w.get("keywords"), key
        assert w.get("sources"), f"{key}: cite where membership came from"
        assert w["steps"], key
        for s in w["steps"]:
            assert s["repo"] in REPOS, (key, s)
            assert isinstance(s["form_id"], str) and s["form_id"], (key, s)
            assert s.get("role"), (key, s["form_id"], "every step needs a role")
            assert isinstance(s.get("inferred"), bool), (
                key, s["form_id"], "inferred must be explicit true/false")


def test_workflows_span_multiple_repos():
    wf, _ = _load()
    for key, w in wf.items():
        repos = {s["repo"] for s in w["steps"]}
        assert len(repos) >= 2, f"{key} is not a cross-repo workflow: {repos}"
