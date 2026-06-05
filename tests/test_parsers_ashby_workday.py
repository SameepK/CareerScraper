from app.parsers.ashby import parse as ashby_parse
from app.parsers.workday import parse as wd_parse

ASHBY_HTML = """
<html><body>
  <a href="/acme/abc-123-uuid-0001">
    <div class="ashby-job-posting-brief">
      <h3 class="ashby-job-posting-brief-title">Frontend Engineer</h3>
      <div class="ashby-job-posting-brief-details"><p>Engineering · Remote · Full-time</p></div>
    </div>
  </a>
  <a href="/acme/def-456-uuid-0002">
    <div class="ashby-job-posting-brief">
      <h3 class="ashby-job-posting-brief-title">Backend Engineer</h3>
      <div class="ashby-job-posting-brief-details"><p>Engineering · New York, NY · Full-time</p></div>
    </div>
  </a>
</body></html>
"""

WORKDAY_HTML = """
<html><body>
  <ul>
    <li>
      <a data-automation-id="jobTitle" href="/jobs/1">ML Engineer</a>
      <dd data-automation-id="locations">Austin, TX</dd>
    </li>
    <li>
      <a data-automation-id="jobTitle" href="/jobs/2">DevOps Engineer</a>
      <dd data-automation-id="locations">Chicago, IL</dd>
    </li>
  </ul>
</body></html>
"""


def test_ashby_board():
    jobs = ashby_parse(ASHBY_HTML, "https://acme.ashbyhq.com")
    assert len(jobs) == 2
    assert jobs[0].title == "Frontend Engineer"
    assert jobs[0].location == "Remote"
    assert "abc-123" in jobs[0].url


def test_workday_board():
    jobs = wd_parse(WORKDAY_HTML, "https://acme.myworkdayjobs.com")
    assert len(jobs) == 2
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].location == "Austin, TX"
