from app.matcher.scorer import score_jobs
from app.models.job import JobListing

RESUME = """
Software engineer with 5 years experience in Python, FastAPI, PostgreSQL, Docker,
Kubernetes, machine learning, scikit-learn, data pipelines, REST APIs, and cloud (AWS).
Led backend teams, shipped production ML models, strong communication skills.
"""

JOBS = [
    JobListing(
        title="Senior Python Backend Engineer",
        description="We need Python, FastAPI, Docker, Kubernetes, REST APIs, PostgreSQL.",
        location="Remote",
        url="https://jobs.example.com/1",
    ),
    JobListing(
        title="iOS Mobile Developer",
        description="Swift, Xcode, UIKit, CoreData, Objective-C, App Store deployment.",
        location="New York, NY",
        url="https://jobs.example.com/2",
    ),
    JobListing(
        title="Data Scientist",
        description="Python, scikit-learn, pandas, machine learning, data pipelines, AWS.",
        location="San Francisco, CA",
        url="https://jobs.example.com/3",
    ),
]


def test_score_jobs_returns_all():
    results = score_jobs(RESUME, JOBS)
    assert len(results) == 3


def test_sorted_descending():
    results = score_jobs(RESUME, JOBS)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_python_job_beats_ios():
    results = score_jobs(RESUME, JOBS)
    urls = [r.job.url for r in results]
    ios_rank = urls.index("https://jobs.example.com/2")
    python_rank = urls.index("https://jobs.example.com/1")
    assert python_rank < ios_rank


def test_matched_keywords_nonempty_for_good_match():
    results = score_jobs(RESUME, JOBS)
    top = results[0]
    assert len(top.matched_keywords) > 0


def test_explanation_contains_score():
    results = score_jobs(RESUME, JOBS)
    for r in results:
        assert str(r.score_pct) in r.explanation


def test_empty_jobs():
    assert score_jobs(RESUME, []) == []


def test_score_pct_range():
    results = score_jobs(RESUME, JOBS)
    for r in results:
        assert 0 <= r.score_pct <= 100
