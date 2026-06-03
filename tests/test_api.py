"""Integration tests for FastAPI endpoints using mocked scrape."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.job import JobListing
from app.scrapers.ats_detector import ATS

SAMPLE_JOBS = [
    JobListing(title="Python Engineer", description="Python FastAPI Docker", location="Remote", url="https://jobs.example.com/1"),
    JobListing(title="iOS Dev", description="Swift Xcode UIKit", location="NYC", url="https://jobs.example.com/2"),
]

RESUME = "Python engineer with FastAPI, Docker, REST APIs experience."


@pytest.fixture
def mock_scrape():
    with patch("app.main.scrape", new_callable=AsyncMock, return_value=(SAMPLE_JOBS, ATS.GENERIC)) as m:
        yield m


@pytest.mark.asyncio
async def test_scrape_endpoint(mock_scrape):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/scrape", json={"url": "https://careers.acme.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ats"] == "generic"
    assert len(data["jobs"]) == 2
    assert data["jobs"][0]["title"] == "Python Engineer"


@pytest.mark.asyncio
async def test_match_endpoint(mock_scrape):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/match", json={"url": "https://careers.acme.com", "resume_text": RESUME})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 2
    # Python job should rank above iOS job
    assert data["results"][0]["job"]["title"] == "Python Engineer"
    assert "score_pct" in data["results"][0]
    assert "explanation" in data["results"][0]
    assert "matched_keywords" in data["results"][0]


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
