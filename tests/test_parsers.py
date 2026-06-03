import pytest
from app.parsers.greenhouse import parse as gh_parse
from app.parsers.lever import parse as lv_parse
from app.parsers.generic import parse as gen_parse

GREENHOUSE_BOARD_HTML = """
<html><body>
<section class="level-0">
  <span class="category-label">Engineering</span>
  <div class="opening">
    <a href="/acme/jobs/1">Senior Engineer</a>
    <span class="location">Remote</span>
  </div>
  <div class="opening">
    <a href="/acme/jobs/2">Staff Engineer</a>
    <span class="location">New York, NY</span>
  </div>
</section>
</body></html>
"""

LEVER_BOARD_HTML = """
<html><body>
  <div class="posting">
    <a class="posting-title" href="https://jobs.lever.co/acme/abc">
      <h5>Product Designer</h5>
    </a>
    <span class="location">San Francisco, CA</span>
  </div>
  <div class="posting">
    <a class="posting-title" href="https://jobs.lever.co/acme/def">
      <h5>Data Scientist</h5>
    </a>
    <span class="location">Remote</span>
  </div>
</body></html>
"""

GENERIC_HTML = """
<html><body>
  <div class="job-card"><a href="/jobs/1">ML Engineer</a><span class="location">Austin, TX</span></div>
  <div class="job-card"><a href="/jobs/2">Backend Dev</a><span class="location">Chicago, IL</span></div>
</body></html>
"""


def test_greenhouse_board():
    jobs = gh_parse(GREENHOUSE_BOARD_HTML, "https://boards.greenhouse.io/acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Senior Engineer"
    assert jobs[0].location == "Remote"
    assert "boards.greenhouse.io" in jobs[0].url


def test_lever_board():
    jobs = lv_parse(LEVER_BOARD_HTML, "https://jobs.lever.co/acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Product Designer"
    assert jobs[0].location == "San Francisco, CA"


def test_generic_cards():
    jobs = gen_parse(GENERIC_HTML, "https://careers.acme.com")
    assert len(jobs) == 2
    titles = {j.title for j in jobs}
    assert "ML Engineer" in titles
