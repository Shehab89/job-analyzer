import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyzer  # noqa: E402
import insights as ins  # noqa: E402
import scraper  # noqa: E402
import skills_catalog as catalog  # noqa: E402
from sample_data import load_sample_jobs  # noqa: E402

POSTING = """Senior Data Engineer (Amsterdam, hybrid)
We need 5+ years of experience with Python, SQL and Apache Spark on Azure.
Experience with Docker, Kubernetes and dbt is a plus. A Master's degree is preferred.
Strong communication skills and a team player. Salary: €70,000 - €90,000 per year."""


def test_catalog_matching_and_normalizing():
    assert catalog.find_tech_skills("We use Python, C++ and C# for REST APIs") == ["Python", "C#", "C++", "REST APIs"]
    assert "Go" not in catalog.find_tech_skills("You will go the extra mile")
    assert "R" not in catalog.find_tech_skills("R&D department")
    assert catalog.find_tools("pyspark and k8s on Google Cloud") == ["GCP", "Kubernetes", "Spark"]
    assert catalog.normalize("sklearn") == "scikit-learn"
    assert catalog.normalize("powerbi") == "Power BI"
    assert catalog.normalize("LangChain") == "LangChain"


def test_rules_extractor():
    facts = analyzer.extract_with_rules(POSTING, "Senior Data Engineer")
    assert {"Python", "SQL"} <= set(facts["tech_skills"])
    assert {"Spark", "Azure", "Docker", "Kubernetes", "dbt"} <= set(facts["tools"])
    assert facts["years_experience"] == 5
    assert (facts["salary_min"], facts["salary_max"], facts["salary_currency"]) == (70_000, 90_000, "EUR")
    assert facts["work_mode"] == "Hybrid"
    assert facts["education"] == "Master"
    assert facts["seniority"] == "Senior"


@pytest.mark.parametrize("text, expected", [
    ("$120k - $150k", (120_000, 150_000, "USD")),
    ("£4,000 - £5,000 per month", (48_000, 60_000, "GBP")),
    ("between 3-5 years", (None, None, None)),
    ("€ 55.000 – € 65.000", (55_000, 65_000, "EUR")),
])
def test_parse_salary(text, expected):
    assert analyzer.parse_salary(text) == expected


def test_ai_path_is_normalized_and_falls_back():
    job = {"title": "Data Engineer", "description": POSTING}
    ai_facts = {"tech_skills": ["python", "Python 3", "SQL"], "tools": ["pyspark"], "soft_skills": [],
                "years_experience": 5, "seniority": "Mid-Senior level", "work_mode": "hybrid",
                "salary_min": 70000, "salary_max": 90000, "salary_currency": "eur", "education": "MSc"}
    with patch.object(analyzer, "extract_with_ai", return_value=ai_facts):
        (result,), warnings = analyzer.analyze_jobs([job], api_key="k", model="m")
    assert result["tech_skills"] == ["Python", "SQL"]
    assert result["tools"] == ["Spark"]
    assert result["seniority"] == "Mid-level" and result["work_mode"] == "Hybrid"
    assert result["education"] == "Master" and result["salary_currency"] == "EUR"
    assert result["extracted_by"] == "AI" and not warnings

    with patch.object(analyzer, "extract_with_ai", side_effect=RuntimeError("quota")):
        (result,), warnings = analyzer.analyze_jobs([job], api_key="k", model="m")
    assert result["extracted_by"] == "Rules" and "Python" in result["tech_skills"]
    assert warnings and "quota" in warnings[0]


def test_salary_hint_used_when_text_has_none():
    job = scraper.make_job(title="Dev", company="A", description="Python developer. " * 5,
                           salary_min_hint=50_000.0, salary_max_hint=60_000.0, salary_currency_hint="EUR")
    (result,), _ = analyzer.analyze_jobs([job])
    assert (result["salary_min"], result["salary_max"], result["salary_currency"]) == (50_000, 60_000, "EUR")


def test_source_adapters():
    jobspy_row = {"site": "linkedin", "title": "Data Analyst", "company": "Acme", "location": "Utrecht, NL",
                  "description": "x" * 60, "job_url": "https://example.com/1", "min_amount": 4000.0,
                  "max_amount": 5000.0, "interval": "monthly", "currency": "EUR", "is_remote": True,
                  "job_level": float("nan"), "date_posted": None}
    job = scraper.jobspy_row_to_job(jobspy_row)
    assert job["source"] == "Linkedin" and job["salary_min_hint"] == 48_000 and job["work_mode_hint"] == "Remote"
    assert job["experience_level"] is None

    adzuna = {"title": "BI Developer", "company": {"display_name": "Acme"}, "location": {"display_name": "Rotterdam"},
              "description": "y" * 60, "redirect_url": "https://example.com/2", "salary_min": 50000,
              "salary_max": 60000, "category": {"label": "IT Jobs"}}
    job = scraper.adzuna_result_to_job(adzuna, "nl")
    assert (job["company"], job["location"], job["salary_currency_hint"]) == ("Acme", "Rotterdam", "EUR")

    apify = {"title": "ML Engineer", "companyName": "Acme", "location": "Remote", "description": "z" * 60,
             "jobUrl": "https://example.com/3", "experienceLevel": "Mid-Senior level"}
    job = scraper.apify_item_to_job(apify)
    assert job["url"] == "https://example.com/3" and job["experience_level"] == "Mid-Senior level"

    dupes = [scraper.make_job(title="A", company="B", description="d" * 60)] * 3
    assert len(scraper.dedupe(dupes, 10)) == 1


def test_insights_on_demo_data():
    jobs, warnings = analyzer.analyze_jobs(load_sample_jobs())
    df = ins.to_frame(jobs)
    assert len(df) == 60 and not warnings
    assert df["years_experience"].notna().all()
    assert df["salary_mid"].notna().mean() > 0.4
    assert df["work_mode"].notna().all()

    top = ins.count_items(df, "tech_skills")
    assert top.iloc[0]["Item"] in {"Python", "SQL"}
    assert 0 < top.iloc[0]["Share"] <= 1

    matrix = ins.cooccurrence(df)
    assert (matrix.values == matrix.values.T).all()

    lines = ins.key_insights(df)
    assert len(lines) >= 5

    per_job, missing = ins.skill_match(df, ["python", "sql"])
    assert per_job["Match"].between(0, 1).all()
    assert "Python" not in set(missing["Item"])


def test_insights_handle_empty_lists():
    df = ins.to_frame([{"title": "t", "company": "c", "tech_skills": [], "tools": [], "soft_skills": [],
                        "years_experience": None, "salary_min": None, "salary_max": None,
                        "salary_currency": None, "work_mode": None, "seniority": None}])
    assert ins.count_items(df, "tech_skills").empty
    assert isinstance(ins.key_insights(df), list)
    assert ins.salary_frame(df)[1] is None
    assert isinstance(ins.cooccurrence(df), pd.DataFrame)
