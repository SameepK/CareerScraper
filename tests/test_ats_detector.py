import pytest
from app.scrapers.ats_detector import detect_ats, ATS


@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/acme/jobs/123", ATS.GREENHOUSE),
    ("https://jobs.lever.co/acme/abc-123", ATS.LEVER),
    ("https://acme.ashbyhq.com/jobs", ATS.ASHBY),
    ("https://acme.myworkdayjobs.com/careers", ATS.WORKDAY),
    ("https://careers.randomco.com/openings", ATS.GENERIC),
])
def test_detect_ats(url: str, expected: ATS) -> None:
    assert detect_ats(url) == expected
