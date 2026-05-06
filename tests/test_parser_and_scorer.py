import pytest

from hunter_tools.models import SearchResult
from hunter_tools.parser import filter_profile_results, guess_location, guess_yoe, normalize_profile_url
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


def test_guess_yoe_extracts_largest_year_value():
    text = "HRBP with 5+ years experience, total 8 years in people management."
    assert guess_yoe(text) == "8"


def test_guess_location_only_uses_current_location_prefix():
    snippet = "中国 上海市 · HRBP · BORGWARD International. Stuttgart Area, Germany."
    assert guess_location(snippet, ["Frankfurt", "Germany"]) == "中国 上海市"


def test_guess_location_matches_current_location_prefix():
    snippet = "Frankfurt, Hesse, Germany · HR Business Partner · Employee relations."
    assert guess_location(snippet, ["Frankfurt", "Germany"]) == "Frankfurt, Hesse, Germany"


def test_guess_location_extracts_non_target_current_location():
    snippet = "Jiangsu, China · Senior HRBP · Employee relations and talent management."
    assert guess_location(snippet, ["Frankfurt", "Germany"]) == "Jiangsu, China"


def test_guess_location_extracts_generic_region_without_city_whitelist():
    snippet = "London Area, United Kingdom · Senior Software Engineer · Platform systems."
    assert guess_location(snippet, ["England"]) == "London Area, United Kingdom"


def test_guess_location_strips_location_label_prefix():
    snippet = "Location: Greater Paris Metropolitan Region · Talent Acquisition Lead"
    assert guess_location(snippet, ["France"]) == "Greater Paris Metropolitan Region"


def test_guess_location_does_not_treat_comma_only_role_as_location():
    snippet = "Engineering Manager, Platform · Paris, France · Distributed systems."
    assert guess_location(snippet, ["France"]) == ""


def test_score_text_returns_nonzero_for_matching_terms():
    context = load_scoring_context(
        job_title="HRBP",
        location_terms=["Frankfurt", "Germany"],
    )
    score, hits, breakdown = score_text(
        "HR Business Partner in Frankfurt with Mandarin and employee relations experience",
        context=context,
        location_text="Frankfurt",
    )
    assert score >= 8
    assert any("skills:employee relations" == hit for hit in hits)
    assert "skills" in breakdown


def test_location_score_uses_location_guess_not_full_text():
    context = load_scoring_context(
        job_title="HRBP",
        location_terms=["Frankfurt", "Germany"],
    )
    score, hits, breakdown = score_text(
        "HR Business Partner in China supporting Germany headquarters",
        context=context,
        location_text="",
    )
    assert "location:Germany" not in hits
    assert breakdown["location"]["delta"] == 0


def test_load_scoring_context_requires_dictionary_file():
    try:
        load_scoring_context(job_title="Non Existing Role", location_terms=["Berlin"])
    except FileNotFoundError:
        assert True
    else:
        assert False, "Expected FileNotFoundError for missing score dictionary"


def test_seniority_list_weight_applies_by_hit_sub_dimension(monkeypatch):
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
    score, hits, breakdown = scorer.score_text("regional manager", context=context)
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


def test_seniority_yoe_token_matches_without_keyword(monkeypatch):
    monkeypatch.setattr(
        scorer,
        "_load_score_dictionary",
        lambda _: {
            "seniority": {
                "junior": ["yoe:0-2"],
                "mid": ["yoe:3-7"],
                "senior": ["yoe:8+"],
            }
        },
    )
    monkeypatch.setattr(scorer, "_load_score_config", lambda: ({"seniority": [1, 2, 3]}, {"seniority": "once"}))

    context = scorer.load_scoring_context("SDE", [])
    score, hits, breakdown = scorer.score_text("candidate has 9 years of experience", context=context)
    assert score == 3
    assert "seniority:yoe:8+" in hits
    assert breakdown["seniority"]["sub_dim"] == "senior"


def test_seniority_per_hit_counts_per_sub_dim_not_per_evidence(monkeypatch):
    monkeypatch.setattr(
        scorer,
        "_load_score_dictionary",
        lambda _: {
            "seniority": {
                "mid": ["Software Engineer", "yoe:3-7"],
            }
        },
    )
    monkeypatch.setattr(scorer, "_load_score_config", lambda: ({"seniority": [2]}, {"seniority": "per_hit"}))

    context = scorer.load_scoring_context("SDE", [])
    score, _, breakdown = scorer.score_text("Software Engineer with 5 years of experience", context=context)
    assert score == 2
    assert breakdown["seniority"]["sub_breakdown"][0]["hit_count"] == 1
