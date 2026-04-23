from hunter_tools.google_client import GoogleClient
from hunter_tools.models import SearchInput, SearchResult
from hunter_tools.pipeline import run_pipeline


def test_antibot_response_detection():
    class DummyResponse:
        status_code = 200
        url = "https://www.google.com/sorry/index?continue=abc"
        text = "Our systems have detected unusual traffic from your computer network."

    assert GoogleClient._is_antibot_response(DummyResponse()) is True


def test_pipeline_skips_failed_query_when_not_fail_fast():
    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def search(self, query, pages=2, page_size=10, delay_seconds=1.5):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary blocked")
            return [
                SearchResult(
                    title="Jane Doe - HR Business Partner | LinkedIn",
                    link="https://www.linkedin.com/in/jane-doe/",
                    snippet="HR Business Partner in Frankfurt, Mandarin, employee relations",
                    query=query,
                )
            ]

    _, candidates = run_pipeline(
        SearchInput(job_title="HRBP", location="Frankfurt", yoe=5, args=["Mandarin"]),
        client=FlakyClient(),
        fail_fast=False,
    )
    assert len(candidates) >= 1

