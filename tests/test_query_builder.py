from hunter_tools.models import SearchInput
from hunter_tools.query_builder import build_queries


def test_build_queries_generates_expected_range():
    payload = SearchInput(
        job_title="HRBP",
        location="Frankfurt",
        yoe=5,
        search_args=["Mandarin", "employee relations"],
    )
    queries = build_queries(payload)
    assert 2 <= len(queries) <= 5
    assert all("site:linkedin.com/in" in query for query in queries)
    assert any("Frankfurt" in query for query in queries)
    assert any("-jobs -hiring -recruiter" in query for query in queries)


def test_build_queries_has_high_recall_baseline():
    payload = SearchInput(
        job_title="HRBP",
        location="Berlin",
        yoe=6,
        search_args=["Mandarin", "employee relations"],
    )
    queries = build_queries(payload)
    baseline = queries[0]
    assert "Mandarin" in baseline
    assert "employee relations" in baseline
    assert len(queries) >= 2


def test_search_args_only_applied_to_shortest_query():
    payload = SearchInput(
        job_title="HRBP",
        location="Frankfurt",
        yoe=5,
        search_args=["Mandarin"],
    )
    queries = build_queries(payload)
    assert "Mandarin" in queries[0]
    assert all("Mandarin" not in query for query in queries[1:])


def test_query_builder_supports_title_alias_off():
    payload = SearchInput(
        job_title="HRBP",
        location="Frankfurt",
        yoe=5,
        title_alias_mode="off",
        location_mode="expanded",
    )
    queries = build_queries(payload)
    assert all("HR Business Partner" not in query for query in queries)
    assert all("Human Resources Business Partner" not in query for query in queries)


def test_query_builder_supports_location_strict():
    payload = SearchInput(
        job_title="HRBP",
        location="Frankfurt",
        yoe=5,
        title_alias_mode="off",
        location_mode="strict",
    )
    queries = build_queries(payload)
    assert len(queries) == 1
    assert "Germany" not in queries[0]
    assert "Frankfurt" in queries[0]


def test_query_builder_location_expand_level_changes_terms():
    low = build_queries(
        SearchInput(
            job_title="SDE",
            location="Frankfurt",
            yoe=3,
            location_mode="expanded",
            location_expand_level=1,
        )
    )
    wide = build_queries(
        SearchInput(
            job_title="SDE",
            location="Frankfurt",
            yoe=3,
            location_mode="expanded",
            location_expand_level=3,
        )
    )
    assert "Hesse" not in low[0]
    assert "Hesse" in wide[0]
