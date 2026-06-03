from pydantic import BaseModel
from app.models.job import JobListing


class MatchedJob(BaseModel):
    job: JobListing
    score: float                   # 0.0 – 1.0
    score_pct: int                 # 0 – 100
    matched_keywords: list[str]
    missing_keywords: list[str]
    explanation: str


class MatchRequest(BaseModel):
    url: str
    resume_text: str


class MatchResponse(BaseModel):
    ats: str
    source_url: str
    results: list[MatchedJob]      # sorted by score desc
