from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.models.job import ScrapeRequest, ScrapeResponse
from app.models.match import MatchRequest, MatchResponse
from app.scrapers.pipeline import scrape
from app.matcher.scorer import score_jobs

app = FastAPI(title="CareerScraper", version="0.1.0")

# Allow the frontend (file:// or any localhost origin) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_jobs(body: ScrapeRequest) -> ScrapeResponse:
    try:
        jobs, ats = await scrape(body.url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ScrapeResponse(jobs=jobs, ats=ats.value, source_url=body.url)


@app.post("/match", response_model=MatchResponse)
async def match_jobs(body: MatchRequest) -> MatchResponse:
    try:
        jobs, ats = await scrape(body.url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    from app.scrapers.description_enricher import enrich_descriptions
    jobs = await enrich_descriptions(jobs, ats.value)

    results = score_jobs(body.resume_text, jobs)
    return MatchResponse(ats=ats.value, source_url=body.url, results=results)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
