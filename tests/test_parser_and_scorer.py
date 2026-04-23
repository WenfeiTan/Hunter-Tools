import pytest

from hunter_tools.models import SearchResult
from hunter_tools.parser import filter_profile_results, normalize_profile_url
from hunter_tools import scorer
from hunter_tools.scorer import load_scoring_context, score_text


def test_filter_profile_results_keeps_only_linkedin_profiles():
    results = [
        SearchResult("A", "https://www.linkedin.com/in/test-user/", "snippet", "q1"),
        SearchResult("B", "https://www.linkedin.com/company/test/", "snippet", "q1"),
    ]
    filtered = filter_profile_results(results)
    assert len(filtered) == 1
    assert normalize_profile_url(filtered[0].link) == "https://www.linkedin.com/in/test-user"


def test_score_text_returns_nonzero_for_matching_terms():
    context = load_scoring_context(
        job_title="HRBP",
        location_terms=["Frankfurt", "Germany"],
    )
    score, hits, breakdown = score_text(
        "HR Business Partner in Frankfurt with Mandarin and employee relations experience",
        yoe=5,
        context=context,
    )
    assert score >= 8
    assert any("skills:employee relations" == hit for hit in hits)
    assert "skills" in breakdown


def test_load_scoring_context_requires_dictionary_file():
    try:
        load_scoring_context(job_title="Non Existing Role", location_terms=["Berlin"])
    except FileNotFoundError:
        assert True
    else:
        assert False, "Expected FileNotFoundError for missing score dictionary"


def test_seniority_list_weight_applies_by_band(monkeypatch):
    monkeypatch.setattr(
        scorer,
        "_load_score_dictionary",
        lambda _: {
            "seniority": {
                "junior": ["assistant"],
                "mid": ["manager"],
                "senior": ["director"],
            }
        },
    )
    monkeypatch.setattr(scorer, "_load_score_config", lambda: ({"seniority": [1, 2, 3]}, {"seniority": "once"}))

    context = scorer.load_scoring_context("HRBP", [])
    score, hits, breakdown = scorer.score_text("regional manager", yoe=5, context=context)
    assert score == 2
    assert "seniority:manager" in hits
    assert breakdown["seniority"]["delta"] == 2


def test_seniority_list_weight_mismatch_raises(monkeypatch):
    monkeypatch.setattr(
        scorer,
        "_load_score_dictionary",
        lambda _: {
            "seniority": {
                "junior": ["assistant"],
                "mid": ["manager"],
                "senior": ["director"],
            }
        },
    )
    monkeypatch.setattr(scorer, "_load_score_config", lambda: ({"seniority": [1, 2]}, {"seniority": "once"}))

    with pytest.raises(ValueError, match="Weight mismatch"):
        scorer.load_scoring_context("HRBP", [])


def test_mode_dimension_mismatch_raises(monkeypatch):
    monkeypatch.setattr(
        scorer,
        "_load_score_dictionary",
        lambda _: {
            "title": ["engineer"],
        },
    )
    monkeypatch.setattr(scorer, "_load_score_config", lambda: ({"title": 3}, {"seniority": "once"}))

    with pytest.raises(ValueError, match="Score dimensions mismatch"):
        scorer.load_scoring_context("HRBP", [])
