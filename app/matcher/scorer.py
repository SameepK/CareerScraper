"""TF-IDF resume ↔ job matcher with keyword explanation."""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.models.job import JobListing
from app.models.match import MatchedJob

# Stop words that carry no signal for job matching
_STOP = frozenset(
    "a an the and or but in on at to for of with is are was were be been "
    "have has had do does did will would could should may might must can "
    "i we you he she they it this that these those our your their".split()
)

_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#./-]*")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 2]


def _keywords(text: str, n: int = 30) -> set[str]:
    """Return the top-n TF-IDF terms from a single document."""
    tokens = _tokenize(text)
    if not tokens:
        return set()
    vec = TfidfVectorizer(analyzer=lambda t: t, max_features=n)
    vec.fit([tokens])
    return set(vec.get_feature_names_out())


def _explain(matched: list[str], missing: list[str], score_pct: int) -> str:
    parts: list[str] = []
    if score_pct >= 75:
        parts.append(f"Strong match ({score_pct}%).")
    elif score_pct >= 50:
        parts.append(f"Moderate match ({score_pct}%).")
    else:
        parts.append(f"Weak match ({score_pct}%).")

    if matched:
        parts.append(f"Shared skills: {', '.join(matched[:8])}.")
    if missing:
        parts.append(f"Gap areas: {', '.join(missing[:5])}.")
    return " ".join(parts)


def score_jobs(resume_text: str, jobs: list[JobListing]) -> list[MatchedJob]:
    """Score every job against the resume, return list sorted by score desc."""
    if not jobs:
        return []

    resume_tokens = _tokenize(resume_text)
    corpus = [resume_tokens] + [_tokenize(f"{j.title} {j.description}") for j in jobs]

    vec = TfidfVectorizer(analyzer=lambda t: t)
    tfidf = vec.fit_transform(corpus)
    feature_names: list[str] = list(vec.get_feature_names_out())

    resume_vec = tfidf[0]
    resume_kws = _keywords(resume_text, n=50)

    results: list[MatchedJob] = []
    for idx, job in enumerate(jobs):
        job_vec = tfidf[idx + 1]
        score: float = float(cosine_similarity(resume_vec, job_vec)[0][0])
        score_pct = min(100, round(score * 200))  # cosine ≤0.5 in practice; scale to 100

        job_kws = _keywords(f"{job.title} {job.description}", n=30)
        matched = sorted(resume_kws & job_kws)
        missing = sorted(job_kws - resume_kws)

        results.append(MatchedJob(
            job=job,
            score=round(score, 4),
            score_pct=score_pct,
            matched_keywords=matched[:10],
            missing_keywords=missing[:10],
            explanation=_explain(matched, missing, score_pct),
        ))

    results.sort(key=lambda r: r.score, reverse=True)
    return results
