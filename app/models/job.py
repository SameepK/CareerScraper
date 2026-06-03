from pydantic import BaseModel, HttpUrl
from typing import Optional


class ScrapeRequest(BaseModel):
    url: str
    resume_text: Optional[str] = None


class JobListing(BaseModel):
    title: str
    description: str
    location: str
    url: str


class ScrapeResponse(BaseModel):
    jobs: list[JobListing]
    ats: str
    source_url: str
