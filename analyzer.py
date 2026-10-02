"""Turns raw job descriptions into structured facts (skills, tools, experience, salary, ...).

Two extractors:
  * AI (Gemini)  - most accurate, used when GEMINI_API_KEY is set.
  * Rules        - keyword/regex based, free and offline. Used when there is no key,
                   or as a fallback when an AI call fails, so the app always works.
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from pydantic import BaseModel, Field

import skills_catalog as catalog

SENIORITY_LEVELS = ["Internship", "Junior", "Mid-level", "Senior", "Lead / Principal", "Manager"]
WORK_MODES = ["Remote", "Hybrid", "On-site"]


class JobFacts(BaseModel):
    """Schema the AI must fill in. Kept flat and simple so every model handles it well."""

    tech_skills: list[str] = Field(description="Technical skills / methods explicitly required, e.g. Python, SQL, Machine Learning")
    tools: list[str] = Field(description="Named tools, platforms, frameworks, e.g. AWS, Docker, Power BI")
    soft_skills: list[str] = Field(description="Soft skills or spoken languages explicitly asked for")
    years_experience: float | None = Field(description="Minimum years of experience required; null if not stated")
    seniority: str | None = Field(description=f"One of: {', '.join(SENIORITY_LEVELS)}; null if unclear")
    work_mode: str | None = Field(description=f"One of: {', '.join(WORK_MODES)}; null if not stated")
    salary_min: float | None = Field(description="Lowest yearly salary mentioned (convert monthly/hourly to yearly); null if none")
    salary_max: float | None = Field(description="Highest yearly salary mentioned; null if none")
    salary_currency: str | None = Field(description="ISO currency code like EUR, USD, GBP; null if none")
    education: str | None = Field(description="Minimum degree required, e.g. Bachelor, Master, PhD; null if not stated")


PROMPT = """You are a strict data extractor for job postings.
Extract ONLY what is explicitly stated in the posting below. Do not guess or add typical requirements.
Use short canonical names (e.g. "Python", "Power BI", "Machine Learning"), one item per skill.

Job posting:
\"\"\"
{text}
\"\"\"
"""


# --------------------------------------------------------------------------- rules extractor

_YEARS_RE = re.compile(
    r"(\d{1,2})(?:\s*(?:-|–|to)\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?)(?:['’]s?)?\s*(?:of\s+)?"
    r"(?:\w+\s+){0,3}?(?:experience|exp\b)",
    re.IGNORECASE,
)
_CURRENCY = {"€": "EUR", "$": "USD", "£": "GBP", "eur": "EUR", "usd": "USD", "gbp": "GBP"}
_MONEY = r"(€|\$|£|eur|usd|gbp)?\s?(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)\s?(k)?"
_SALARY_RE = re.compile(
    _MONEY + r"\s*(?:-|–|to)\s*" + _MONEY
    + r"(?:\s*(?:per|a|/)\s*(year|yr|annum|month|mo|hour|hr))?",
    re.IGNORECASE,
)
_PERIOD_TO_YEAR = {"month": 12, "mo": 12, "hour": 1800, "hr": 1800}


def _to_number(raw, k):
    digits = re.sub(r"[.,\s](?=\d{3}\b)", "", raw).replace(",", ".")
    value = float(digits)
    return value * 1000 if k else value


def parse_salary(text):
    """Find a salary range like '€60,000 - €80,000' or '$120k-150k per year'. Returns yearly values."""
    for m in _SALARY_RE.finditer(text):
        cur1, low, k1, cur2, high, k2, period = m.groups()
        currency = cur1 or cur2
        if not currency:
            continue  # a bare number range (e.g. "3-5 years") is not a salary
        k = k1 or k2
        lo, hi = _to_number(low, k1 or k), _to_number(high, k2 or k)
        multiplier = _PERIOD_TO_YEAR.get((period or "").lower(), 1)
        lo, hi = lo * multiplier, hi * multiplier
        if 5_000 <= lo <= hi <= 2_000_000:
            return lo, hi, _CURRENCY[currency.lower()]
    return None, None, None


def seniority_from_title(title):
    t = (title or "").lower()
    rules = [
        ("Internship", ["intern", "trainee", "stage", "stagiair"]),
        ("Manager", ["manager", "head of", "director", "vp "]),
        ("Lead / Principal", ["lead", "principal", "staff", "architect"]),
        ("Senior", ["senior", "sr.", "sr "]),
        ("Junior", ["junior", "jr.", "jr ", "graduate", "entry"]),
        ("Mid-level", ["medior", "mid-level", "mid level", "intermediate"]),
    ]
    for level, words in rules:
        if any(w in t for w in words):
            return level
    return None


def seniority_from_years(years):
    if years is None:
        return None
    if years < 2:
        return "Junior"
    if years < 5:
        return "Mid-level"
    return "Senior"


def work_mode_from_text(text):
    t = text.lower()
    if "hybrid" in t:
        return "Hybrid"
    if re.search(r"\b(fully remote|100% remote|remote[- ]first|remote position|work from home|remote)\b", t):
        return "Remote"
    if re.search(r"\b(on-site|onsite|on site|in the office|in-office)\b", t):
        return "On-site"
    return None


def education_from_text(text):
    t = text.lower()
    for level, words in [("PhD", ["phd", "doctorate"]), ("Master", ["master", "msc", "m.sc"]),
                         ("Bachelor", ["bachelor", "bsc", "b.sc", "university degree", "degree in"])]:
        if any(w in t for w in words):
            return level
    return None


def extract_with_rules(text, title=""):
    years = [int(y) for y in _YEARS_RE.findall(text) if 0 < int(y) <= 20]
    lo, hi, cur = parse_salary(text)
    min_years = float(min(years)) if years else None
    return {
        "tech_skills": catalog.find_tech_skills(text),
        "tools": catalog.find_tools(text),
        "soft_skills": catalog.find_soft_skills(text),
        "years_experience": min_years,
        "seniority": seniority_from_title(title),
        "work_mode": work_mode_from_text(text),
        "salary_min": lo,
        "salary_max": hi,
        "salary_currency": cur,
        "education": education_from_text(text),
    }


# --------------------------------------------------------------------------- AI extractor

@lru_cache(maxsize=2000)
def extract_with_ai(text, model, api_key):
    """One Gemini call per posting. Cached, so re-running the same search costs nothing.

    Raises on failure; the caller falls back to the rules extractor.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=PROMPT.format(text=text[:8000]),
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=JobFacts,
        ),
    )
    facts = response.parsed
    if facts is None:
        facts = JobFacts.model_validate_json(response.text)
    return facts.model_dump()


# --------------------------------------------------------------------------- merge + clean

def _clean_list(items):
    seen, out = set(), []
    for item in items or []:
        name = catalog.normalize(item)
        if name and name.lower() not in seen and len(name) <= 40:
            seen.add(name.lower())
            out.append(name)
    return out


_SYNONYMS = {
    "Internship": ["intern", "trainee"],
    "Junior": ["junior", "entry", "graduate", "associate"],
    "Mid-level": ["mid", "medior", "intermediate"],
    "Senior": ["senior"],
    "Lead / Principal": ["lead", "principal", "staff", "architect"],
    "Manager": ["manager", "director", "head", "executive"],
    "Remote": ["remote"],
    "Hybrid": ["hybrid"],
    "On-site": ["on-site", "onsite", "on site", "office"],
    "PhD": ["phd", "doctor"],
    "Master": ["master", "msc"],
    "Bachelor": ["bachelor", "bsc", "degree"],
}


def _pick(value, allowed):
    """Map free text like 'remote' or 'Mid-Senior level' onto one of the allowed labels."""
    if not value:
        return None
    v = str(value).lower()
    for label in allowed:
        if any(word in v for word in _SYNONYMS[label]):
            return label
    return None


def finalize(facts, job, source):
    """Clean one extraction result and fill gaps using the scraped metadata and the rules extractor."""
    text = job.get("description", "")
    rules = extract_with_rules(text, job.get("title", "")) if source == "AI" else facts

    years = facts.get("years_experience")
    if years is not None and not (0 <= float(years) <= 30):
        years = None

    seniority = (
        _pick(facts.get("seniority"), SENIORITY_LEVELS)
        or seniority_from_title(job.get("title"))
        or _pick(job.get("experience_level"), SENIORITY_LEVELS)
        or seniority_from_years(years)
    )
    work_mode = (
        _pick(facts.get("work_mode"), WORK_MODES)
        or _pick(job.get("work_mode_hint"), WORK_MODES)
        or rules.get("work_mode")
    )
    salary_min, salary_max = facts.get("salary_min"), facts.get("salary_max")
    currency = facts.get("salary_currency")
    if not salary_min and not salary_max and (job.get("salary_min_hint") or job.get("salary_max_hint")):
        # the job site published a structured salary; use it when the text itself has none
        salary_min, salary_max = job.get("salary_min_hint"), job.get("salary_max_hint")
        currency = job.get("salary_currency_hint")
    if salary_min and not salary_max:
        salary_max = salary_min
    if salary_max and not salary_min:
        salary_min = salary_max
    if salary_min and salary_max and not (5_000 <= float(salary_min) <= float(salary_max) <= 2_000_000):
        salary_min = salary_max = None  # not a plausible yearly salary

    return {
        **job,
        "tech_skills": _clean_list(facts.get("tech_skills")),
        "tools": _clean_list(facts.get("tools")),
        "soft_skills": _clean_list(facts.get("soft_skills")),
        "years_experience": float(years) if years is not None else None,
        "seniority": seniority,
        "work_mode": work_mode,
        "salary_min": float(salary_min) if salary_min else None,
        "salary_max": float(salary_max) if salary_max else None,
        "salary_currency": (currency or "").upper() or None,
        "education": _pick(facts.get("education"), ["PhD", "Master", "Bachelor"]),
        "extracted_by": source,
    }


def analyze_jobs(jobs, api_key=None, model=None, on_progress=None, workers=6):
    """Analyze every job (in parallel) and return enriched job dicts plus a list of warnings."""
    warnings = []

    def work(job):
        text = f"{job.get('title', '')}\n{job.get('description', '')}"
        if api_key:
            try:
                return finalize(extract_with_ai(text, model, api_key), job, "AI"), None
            except Exception as exc:  # quota, network, bad JSON, ... -> keep going offline
                facts = extract_with_rules(text, job.get("title", ""))
                return finalize(facts, job, "Rules"), f"{type(exc).__name__}: {exc}"
        return finalize(extract_with_rules(text, job.get("title", "")), job, "Rules"), None

    results = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, job): i for i, job in enumerate(jobs)}
        for done, future in enumerate(as_completed(futures), start=1):
            i = futures[future]
            results[i], warning = future.result()
            if warning:
                warnings.append(warning)
            if on_progress:
                on_progress(done / len(jobs))
    return results, warnings
