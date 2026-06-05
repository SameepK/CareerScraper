"""TF-IDF resume ↔ job matcher with keyword explanation."""
import re
import numpy as np
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

# Boilerplate JD words that appear in almost every posting — no matching signal
_JD_NOISE = frozenset([
    # Generic JD filler
    "role", "team", "work", "experience", "ability", "strong", "including",
    "across", "build", "building", "drive", "driving", "years", "looking",
    "passionate", "excited", "opportunity", "skills", "required", "preferred",
    "join", "help", "use", "using", "used", "new", "great", "best", "high",
    "well", "also", "make", "ensure", "contribute", "good", "key", "core",
    "within", "following", "understand", "understanding", "knowledge", "ability",
    "responsible", "responsibilities", "qualifications", "requirements",
    "like", "love", "enjoy", "want", "care", "impact", "world", "people",
    "company", "business", "product", "products", "customer", "customers",
    "solutions", "solve", "problems", "problem", "challenges", "challenge",
    "environment", "culture", "values", "mission", "vision", "growth",
    "benefits", "equity", "salary", "compensation", "offer", "offering",
    "apis", "api", "app", "apps", "deploy", "deployment", "scalable", "scale",
    "collaborate", "collaboration", "cross", "functional", "ownership", "own",
    "plus", "bonus", "nice", "have", "degree", "bs", "ms", "phd", "related",
    "field", "equivalent", "practice",
    # Job title words — never useful as skill keywords
    "software", "engineer", "engineering", "developer", "development",
    "manager", "management", "analyst", "associate", "specialist", "lead",
    "senior", "junior", "staff", "principal", "director", "head", "vp",
    "intern", "contract", "full", "time", "part", "remote", "hybrid",
    "levels", "level", "all", "mid", "entry", "backend", "frontend",
    "fullstack", "full-stack", "back-end", "front-end",
])

_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#./-]*")
# Strip trailing punctuation that bleeds in from sentence ends (but keep c++, node.js)
_TRAIL_PUNCT_RE = re.compile(r"[.,:;!?()\[\]]+$")

# Seniority keywords that warrant a penalty for junior candidates
_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|vp|vice\s+president)\b", re.I
)

# Date range patterns: "Jan 2019 – Mar 2022", "2018 - 2021", "2020 – Present"
_DATE_RANGE_RE = re.compile(
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?"
    r"((?:19|20)\d{2})"
    r"\s*[-–—to]+\s*"
    r"((?:19|20)\d{2}|present|current|now)",
    re.I,
)

# Marker for the start of an education section
_EDUCATION_RE = re.compile(
    r"^\s*(education|academic|degree|university|college|school)\b",
    re.I | re.MULTILINE,
)

_CURRENT_YEAR = 2025  # fixed reference year


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    cleaned = [_TRAIL_PUNCT_RE.sub("", t) for t in tokens]
    return [t for t in cleaned if t not in _STOP and t not in _JD_NOISE and len(t) > 2]


def _extract_years_of_experience(resume_text: str) -> float:
    """
    Parse explicit date ranges from the resume and return total years as a float.
    Strips the education section first to avoid counting degree years.
    """
    edu_match = _EDUCATION_RE.search(resume_text)
    work_text = resume_text[: edu_match.start()] if edu_match else resume_text

    total = 0.0
    for m in _DATE_RANGE_RE.finditer(work_text):
        start = int(m.group(1))
        end_raw = m.group(2).lower()
        end = _CURRENT_YEAR if end_raw in ("present", "current", "now") else int(end_raw)
        if end >= start:
            total += end - start
    return total


def _seniority_penalty(job_title: str, resume_years: float) -> float:
    """
    Return a score multiplier in [0.0, 1.0].
    Senior/Staff/Principal/Lead roles get 0.4 when the candidate has < 3 years.
    """
    if _SENIOR_RE.search(job_title) and resume_years < 3:
        return 0.4
    return 1.0


def _top_terms(tfidf_row, feature_names: list[str], n: int = 30) -> set[str]:
    """Return the top-n terms by TF-IDF weight from a sparse matrix row."""
    row = tfidf_row.toarray().ravel()
    top_indices = np.argpartition(row, -min(n, len(row)))[-n:]
    return {feature_names[i] for i in top_indices if row[i] > 0}


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

    resume_years = _extract_years_of_experience(resume_text)

    resume_tokens = _tokenize(resume_text)
    # Weight description 3× over title — title words (role names) carry little
    # skill signal, while requirements/responsibilities sections carry most of it.
    corpus = [resume_tokens] + [
        _tokenize(j.title) + _tokenize(j.description) * 3
        for j in jobs
    ]

    vec = TfidfVectorizer(analyzer=lambda t: t)
    tfidf = vec.fit_transform(corpus)
    feature_names: list[str] = list(vec.get_feature_names_out())

    resume_vec = tfidf[0]
    # Keywords drawn from the corpus-fitted matrix so IDF is meaningful
    resume_kws = _top_terms(resume_vec, feature_names, n=50)

    results: list[MatchedJob] = []
    for idx, job in enumerate(jobs):
        job_vec = tfidf[idx + 1]
        score: float = float(cosine_similarity(resume_vec, job_vec)[0][0])

        penalty = _seniority_penalty(job.title, resume_years)
        score_pct = min(100, round(score * 200 * penalty))  # cosine ≤0.5 in practice; scale to 100

        job_kws = _top_terms(job_vec, feature_names, n=30)
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
