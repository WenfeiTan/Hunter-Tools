from pathlib import Path

from hunter_tools.google_client import GoogleClient, persist_raw_page


def test_parse_google_html_supports_mjjyud_blocks():
    html = """
    <html><body>
      <div class="MjjYud">
        <a href="https://www.linkedin.com/in/jane-doe/">
          <h3>Jane Doe - HR Business Partner</h3>
        </a>
        <div class="VwiC3b">Frankfurt, Germany · HRBP</div>
      </div>
    </body></html>
    """
    results = GoogleClient._parse_google_html(html, "q1")  # pylint: disable=protected-access
    assert len(results) == 1
    assert "linkedin.com/in/jane-doe" in results[0].link


def test_persist_raw_page_writes_html_and_metadata(tmp_path: Path):
    persist_raw_page(
        output_dir=tmp_path,
        query='site:linkedin.com/in "HRBP"',
        page=1,
        start=0,
        html="<html>ok</html>",
        request_url="https://www.google.com/search?q=test",
        final_url="https://www.google.com/search?q=test",
        mode="selenium",
    )
    html_files = list(tmp_path.glob("*.html"))
    json_files = list(tmp_path.glob("*.json"))
    assert len(html_files) == 1
    assert len(json_files) == 1
