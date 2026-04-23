from hunter_tools.models import SearchResult
from hunter_tools.parser import filter_profile_results, normalize_profile_url
from hunter_tools.scorer import score_text


def test_filter_profile_results_keeps_only_linkedin_profiles():
    results = [
        SearchResult("A", "https://www.linkedin.com/in/test-user/", "snippet", "q1"),
        SearchResult("B", "https://www.linkedin.com/company/test/", "snippet", "q1"),
    ]
    filtered = filter_profile_results(results)
    assert len(filtered) == 1
    assert normalize_profile_url(filtered[0].link) == "https://www.linkedin.com/in/test-user"


def test_score_text_returns_nonzero_for_matching_terms():
    score, hits = score_text(
        "HR Business Partner in Frankfurt with Mandarin and employee relations experience",
        location_terms=["Frankfurt", "Germany"],
        yoe=5,
        job_title="HRBP",
        custom_keywords=["Mandarin", "employee relations"],
    )
    assert score >= 8
    assert "employee relations" in hits
