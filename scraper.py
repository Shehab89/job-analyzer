"""Collects job postings from different sources and converts them all into one simple format.

Sources:
  * LinkedIn - free, built-in. Reads LinkedIn's public job pages (no login, no key).
  * JobSpy  - free, optional extra (Indeed / Glassdoor / Google Jobs). No key needed.
  * Adzuna  - official job-search API. Free key from https://developer.adzuna.com. Most reliable.
  * Apify   - paid cloud scraper (LinkedIn actor). Needs APIFY_API_TOKEN.
Demo data lives in sample_data.py.
"""

import math
import re
import time

import streamlit as st

SOURCES = ["LinkedIn (free, built-in)", "JobSpy (free: Indeed, Glassdoor...)", "Adzuna API (free key)",
           "Apify (paid)", "Demo data"]

DATE_POSTED_HOURS = {"Past 24 hours": 24, "Past week": 24 * 7, "Past month": 24 * 30, "Any time": None}

# Country name -> (Indeed country name for JobSpy, Adzuna country code)
COUNTRIES = {
    "Netherlands": ("netherlands", "nl"),
    "Belgium": ("belgium", "be"),
    "Germany": ("germany", "de"),
    "France": ("france", "fr"),
    "United Kingdom": ("uk", "gb"),
    "United States": ("usa", "us"),
    "Canada": ("canada", "ca"),
    "Australia": ("australia", "au"),
    "Spain": ("spain", "es"),
    "Italy": ("italy", "it"),
    "Poland": ("poland", "pl"),
    "Austria": ("austria", "at"),
    "Switzerland": ("switzerland", "ch"),
    "India": ("india", "in"),
}

JOBSPY_SITES = {"Indeed": "indeed", "LinkedIn": "linkedin", "Glassdoor": "glassdoor", "Google Jobs": "google"}

_CURRENCY_BY_COUNTRY = {"nl": "EUR", "be": "EUR", "de": "EUR", "fr": "EUR", "es": "EUR", "it": "EUR", "at": "EUR",
                        "gb": "GBP", "us": "USD", "ca": "CAD", "au": "AUD", "pl": "PLN", "ch": "CHF", "in": "INR"}
_TO_YEARLY = {"yearly": 1, "monthly": 12, "weekly": 52, "daily": 230, "hourly": 1800}


class ScrapeError(RuntimeError):
    """Raised with a message that can be shown to the user as-is."""


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip().lower() in ("", "nan", "none"):
        return None
    return value


def _first(item, *keys):
    """Return the first non-empty value among several possible field names."""
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("display_name") or value.get("name") or value.get("label") or value.get("text")
        value = _clean(value)
        if value not in (None, [], {}):
            return value
    return None


def make_job(**fields):
    job = {
        "title": "Untitled", "company": "Unknown", "location": "Unknown", "description": "",
        "url": None, "source": None, "posted_at": None, "applicants": None,
        "experience_level": None, "employment_type": None, "work_mode_hint": None, "industry": None,
        "salary_min_hint": None, "salary_max_hint": None, "salary_currency_hint": None,
    }
    job.update({k: v for k, v in fields.items() if _clean(v) is not None})
    job["description"] = str(job["description"])
    return job


def dedupe(jobs, limit):
    """Drop repeated postings (same title + company) and postings with too little text to analyse."""
    seen, unique = set(), []
    for job in jobs:
        key = (str(job["title"]).lower().strip(), str(job["company"]).lower().strip())
        if key not in seen and len(job["description"]) > 50:
            seen.add(key)
            unique.append(job)
    return unique[:limit]


# --------------------------------------------------------------------------- LinkedIn (built-in, free)
#
# LinkedIn serves public job listings without login at these "guest" URLs (the same pages
# you see when you open linkedin.com/jobs while logged out). We read the list page by page,
# then open each posting to get its full description. Be gentle: few requests, small pauses.

LINKEDIN_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_POSTING = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
LINKEDIN_WORKPLACE = {"Any": None, "On-site": "1", "Remote": "2", "Hybrid": "3"}
_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


def _get(session, url, params=None, tries=4):
    """GET with polite retries. LinkedIn answers 429 when we go too fast: wait and try again."""
    import requests

    wait = 2
    for attempt in range(tries):
        try:
            resp = session.get(url, params=params, headers=_BROWSER_HEADERS, timeout=20)
        except requests.RequestException as exc:
            if attempt == tries - 1:
                raise ScrapeError(f"Could not reach LinkedIn: {exc}") from exc
        else:
            if resp.status_code == 200:
                return resp.text
            if resp.status_code not in (429, 500, 502, 503, 999):
                return None  # e.g. 400 when paging past the last result
        time.sleep(wait)
        wait *= 2
    return None


def _text(node):
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else None


def parse_linkedin_search(html):
    """Parse one page of search results into basic job cards (no description yet)."""
    from bs4 import BeautifulSoup

    cards = []
    for card in BeautifulSoup(html, "html.parser").select("li"):
        urn = card.select_one("[data-entity-urn]")
        link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        job_id = None
        if urn:
            job_id = urn["data-entity-urn"].rsplit(":", 1)[-1]
        elif link:
            m = re.search(r"-(\d{6,})(?:\?|$)", link["href"]) or re.search(r"/view/(\d+)", link["href"])
            job_id = m.group(1) if m else None
        if not job_id:
            continue
        posted = card.select_one("time")
        cards.append({
            "id": job_id,
            "title": _text(card.select_one(".base-search-card__title, h3")),
            "company": _text(card.select_one(".base-search-card__subtitle, h4")),
            "location": _text(card.select_one(".job-search-card__location")),
            "url": link["href"].split("?")[0] if link else f"https://www.linkedin.com/jobs/view/{job_id}",
            "posted_at": posted.get("datetime") if posted else None,
            "salary_text": _text(card.select_one(".job-search-card__salary-info")),
        })
    return cards


def parse_linkedin_posting(html):
    """Parse a job's detail page: full description plus LinkedIn's 'criteria' (seniority etc.)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    desc = soup.select_one(".show-more-less-html__markup, .description__text")
    criteria = {}
    for item in soup.select(".description__job-criteria-item"):
        key = _text(item.select_one(".description__job-criteria-subheader"))
        value = _text(item.select_one(".description__job-criteria-text"))
        if key and value:
            criteria[key.lower()] = value
    applicants = _text(soup.select_one(".num-applicants__caption"))
    return {
        "description": desc.get_text("\n", strip=True) if desc else "",
        "experience_level": criteria.get("seniority level"),
        "employment_type": criteria.get("employment type"),
        "industry": criteria.get("industries"),
        "applicants": int(re.sub(r"\D", "", applicants)) if applicants and re.search(r"\d", applicants) else None,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def scrape_linkedin_free(job_title, location, max_jobs, date_posted, workplace="Any", _on_progress=None):
    """Free LinkedIn scraper: search pages -> job cards -> each job's full description."""
    import requests

    hours = DATE_POSTED_HOURS.get(date_posted)
    params = {"keywords": job_title, "location": location}
    if hours:
        params["f_TPR"] = f"r{hours * 3600}"
    if LINKEDIN_WORKPLACE.get(workplace):
        params["f_WT"] = LINKEDIN_WORKPLACE[workplace]

    session = requests.Session()
    cards, seen, start = [], set(), 0
    while len(cards) < max_jobs and start < 1000:
        html = _get(session, LINKEDIN_SEARCH, {**params, "start": start})
        page = parse_linkedin_search(html) if html else []
        new = [c for c in page if c["id"] not in seen]
        if not new:
            break
        for c in new:
            seen.add(c["id"])
        cards += new
        start += len(page)
        time.sleep(1.0)
    cards = cards[:max_jobs]
    if not cards:
        raise ScrapeError("LinkedIn returned no jobs. Try a broader title or location, 'Any time', or wait a few "
                          "minutes if you searched a lot (LinkedIn slows down repeated requests).")

    jobs = []
    for i, card in enumerate(cards, start=1):
        html = _get(session, LINKEDIN_POSTING.format(job_id=card["id"]))
        details = parse_linkedin_posting(html) if html else {"description": ""}
        description = details["description"]
        if card.get("salary_text") and card["salary_text"] not in description:
            description += f"\nSalary: {card['salary_text']}"
        jobs.append(make_job(
            title=card["title"], company=card["company"], location=card["location"],
            description=description, url=card["url"], source="LinkedIn", posted_at=card["posted_at"],
            applicants=details.get("applicants"), experience_level=details.get("experience_level"),
            employment_type=details.get("employment_type"), industry=details.get("industry"),
            work_mode_hint=workplace if workplace != "Any" else None,
        ))
        if _on_progress:
            _on_progress(i / len(cards))
        time.sleep(0.6)
    jobs = dedupe(jobs, max_jobs)
    if not jobs:
        raise ScrapeError("LinkedIn listed jobs but did not return their descriptions (probably rate-limited). "
                          "Wait a few minutes and try again with fewer jobs.")
    return jobs


# --------------------------------------------------------------------------- JobSpy (optional extra)

def jobspy_row_to_job(row):
    interval = _clean(row.get("interval"))
    factor = _TO_YEARLY.get(str(interval).lower(), 1) if interval else 1
    lo, hi = _clean(row.get("min_amount")), _clean(row.get("max_amount"))
    remote = _clean(row.get("is_remote"))
    return make_job(
        title=_first(row, "title"),
        company=_first(row, "company"),
        location=_first(row, "location"),
        description=_first(row, "description") or "",
        url=_first(row, "job_url", "job_url_direct"),
        source=str(_first(row, "site") or "jobspy").capitalize(),
        posted_at=str(row["date_posted"]) if _clean(row.get("date_posted")) is not None else None,
        experience_level=_first(row, "job_level"),
        employment_type=_first(row, "job_type"),
        work_mode_hint="Remote" if remote is True else _first(row, "work_from_home_type"),
        industry=_first(row, "company_industry"),
        salary_min_hint=float(lo) * factor if lo else None,
        salary_max_hint=float(hi) * factor if hi else None,
        salary_currency_hint=_first(row, "currency"),
    )


@st.cache_data(ttl=3600, show_spinner=False)
def scrape_jobspy(job_title, location, country, sites, max_jobs, date_posted):
    try:
        from jobspy import scrape_jobs
    except ImportError as exc:
        raise ScrapeError("JobSpy is an optional extra and is not installed. Install it with: "
                          "pip install -r requirements-jobspy.txt   (needs Python 3.10-3.12), "
                          "or use the built-in LinkedIn source.") from exc

    indeed_country = COUNTRIES[country][0]
    try:
        df = scrape_jobs(
            site_name=[JOBSPY_SITES[s] for s in sites],
            search_term=job_title,
            google_search_term=f"{job_title} jobs near {location or country}",
            location=location or country,
            results_wanted=int(max_jobs),
            hours_old=DATE_POSTED_HOURS.get(date_posted),
            country_indeed=indeed_country,
            linkedin_fetch_description=True,  # slower, but we need the full text to analyse
            description_format="markdown",
            verbose=0,
        )
    except Exception as exc:
        raise ScrapeError(
            f"JobSpy could not fetch jobs ({type(exc).__name__}: {exc}). Job sites sometimes block "
            "scrapers for a while; wait a few minutes, choose fewer jobs, or try another site/source."
        ) from exc
    jobs = [jobspy_row_to_job(row) for row in df.to_dict("records")]
    return dedupe(jobs, int(max_jobs) * len(sites))


# --------------------------------------------------------------------------- Adzuna

def adzuna_result_to_job(item, country_code):
    return make_job(
        title=_first(item, "title"),
        company=_first(item, "company"),
        location=_first(item, "location"),
        description=_first(item, "description") or "",
        url=_first(item, "redirect_url"),
        source="Adzuna",
        posted_at=_first(item, "created"),
        employment_type=_first(item, "contract_time"),
        industry=_first(item, "category"),
        salary_min_hint=_first(item, "salary_min"),
        salary_max_hint=_first(item, "salary_max"),
        salary_currency_hint=_CURRENCY_BY_COUNTRY.get(country_code),
    )


@st.cache_data(ttl=3600, show_spinner=False)
def scrape_adzuna(job_title, location, country, max_jobs, date_posted, _app_id, _app_key):
    import requests

    code = COUNTRIES[country][1]
    jobs, page = [], 1
    while len(jobs) < max_jobs and page <= 5:
        params = {
            "app_id": _app_id, "app_key": _app_key, "what": job_title,
            "results_per_page": min(50, int(max_jobs)), "content-type": "application/json",
        }
        if location and location.lower() not in (country.lower(), "remote"):
            params["where"] = location
        hours = DATE_POSTED_HOURS.get(date_posted)
        if hours:
            params["max_days_old"] = max(1, hours // 24)
        try:
            resp = requests.get(f"https://api.adzuna.com/v1/api/jobs/{code}/search/{page}", params=params, timeout=30)
        except requests.RequestException as exc:
            raise ScrapeError(f"Could not reach Adzuna: {exc}") from exc
        if resp.status_code in (401, 403):
            raise ScrapeError("Adzuna rejected the keys. Check ADZUNA_APP_ID and ADZUNA_APP_KEY.")
        if resp.status_code != 200:
            raise ScrapeError(f"Adzuna returned HTTP {resp.status_code}: {resp.text[:200]}")
        results = resp.json().get("results", [])
        if not results:
            break
        jobs += [adzuna_result_to_job(r, code) for r in results]
        page += 1
    return dedupe(jobs, int(max_jobs))


# --------------------------------------------------------------------------- Apify

def apify_item_to_job(item):
    return make_job(
        title=_first(item, "title", "jobTitle", "position"),
        company=_first(item, "companyName", "company", "companyTitle"),
        location=_first(item, "location", "jobLocation", "place"),
        description=_first(item, "description", "descriptionText", "jobDescription") or "",
        url=_first(item, "jobUrl", "link", "url", "applyUrl"),
        source="LinkedIn (Apify)",
        posted_at=_first(item, "publishedAt", "postedAt", "postedTime", "listedAt"),
        applicants=_first(item, "applicationsCount", "applicants", "numApplicants"),
        experience_level=_first(item, "experienceLevel", "seniorityLevel"),
        employment_type=_first(item, "contractType", "employmentType"),
        work_mode_hint=_first(item, "workplaceType", "workRemoteAllowed"),
        industry=_first(item, "sector", "industries", "industry"),
    )


@st.cache_data(ttl=3600, show_spinner=False)
def scrape_apify(job_title, location, max_jobs, date_posted, actor_id, _token):
    from apify_client import ApifyClient

    hours = DATE_POSTED_HOURS.get(date_posted)
    run_input = {
        "title": job_title,
        "location": location,
        "rows": int(max_jobs),
        "publishedAt": f"r{hours * 3600}" if hours else "",
        "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
    }
    try:
        client = ApifyClient(_token)
        run = client.actor(actor_id).call(run_input=run_input, timeout_secs=600)
    except Exception as exc:
        raise ScrapeError(f"Apify run failed: {exc}") from exc
    if not run or run.get("status") not in (None, "SUCCEEDED"):
        raise ScrapeError(f"Apify run ended with status {run.get('status') if run else 'unknown'}")
    items = client.dataset(run["defaultDatasetId"]).list_items().items
    return dedupe([apify_item_to_job(item) for item in items], int(max_jobs))
