"""A realistic but fictional set of job postings, so the app can be tried without any API keys.

Companies and postings are made up. The generator is seeded, so the demo always looks the same.
"""

import random

ROLES = {
    "Data Analyst": {
        "core": ["SQL", "Excel", "Power BI", "Data Visualization", "Statistics"],
        "extra": ["Python", "Tableau", "Data Modeling", "dbt", "Snowflake", "Stakeholder Management"],
        "salary": (42_000, 65_000),
    },
    "Data Engineer": {
        "core": ["Python", "SQL", "ETL", "Spark", "Airflow"],
        "extra": ["Azure", "AWS", "Databricks", "Kafka", "Docker", "Terraform", "dbt", "Snowflake", "CI/CD"],
        "salary": (55_000, 85_000),
    },
    "Data Scientist": {
        "core": ["Python", "Machine Learning", "Statistics", "SQL", "scikit-learn"],
        "extra": ["PyTorch", "TensorFlow", "NLP", "Generative AI", "Spark", "AWS", "Deep Learning"],
        "salary": (55_000, 90_000),
    },
    "Machine Learning Engineer": {
        "core": ["Python", "Machine Learning", "PyTorch", "Docker", "Kubernetes"],
        "extra": ["Generative AI", "AWS", "GCP", "CI/CD", "FastAPI", "Deep Learning", "NLP"],
        "salary": (65_000, 105_000),
    },
    "Python Developer": {
        "core": ["Python", "REST APIs", "Git", "PostgreSQL", "Docker"],
        "extra": ["Django", "FastAPI", "Flask", "AWS", "Testing", "CI/CD", "Redis", "Linux", "Kubernetes"],
        "salary": (48_000, 80_000),
    },
    "BI Developer": {
        "core": ["Power BI", "SQL", "Data Modeling", "ETL"],
        "extra": ["Azure", "Excel", "Tableau", "Snowflake", "Python", "Stakeholder Management"],
        "salary": (45_000, 70_000),
    },
}

LEVELS = [("Junior", 1, 0.75), ("", 3, 1.0), ("Medior", 3, 1.0), ("Senior", 5, 1.3), ("Lead", 8, 1.5)]

COMPANIES = [
    "Northwind Analytics", "Tulip Tech", "Canal Data Labs", "Polder AI", "Windmill Software",
    "Delta Logistics", "Orange Fintech", "Harbor Health", "Bright Energy", "Contoso Retail",
    "Fabrikam Insurance", "Lighthouse Media",
]
LOCATIONS = ["Amsterdam", "Rotterdam", "Utrecht", "Eindhoven", "The Hague", "Remote (Netherlands)"]
SOFT = ["communication skills", "team player", "problem-solving", "stakeholder management",
        "mentoring", "fluent English", "self-starter"]


def load_sample_jobs(n=60, seed=7):
    rng = random.Random(seed)
    jobs = []
    for i in range(n):
        role = rng.choice(list(ROLES))
        spec = ROLES[role]
        level, years, pay_factor = rng.choice(LEVELS)
        years = max(1, years + rng.choice([-1, 0, 0, 1]))
        title = f"{level} {role}".strip()
        company = rng.choice(COMPANIES)
        location = rng.choice(LOCATIONS)

        skills = rng.sample(spec["core"], k=min(len(spec["core"]), rng.randint(3, 5)))
        skills += rng.sample(spec["extra"], k=rng.randint(1, 4))
        soft = rng.sample(SOFT, k=rng.randint(1, 3))

        if "Remote" in location:
            mode_sentence = "This is a fully remote position within the Netherlands."
        else:
            mode_sentence = rng.choice([
                "We work hybrid: 2-3 days in the office, the rest from home.",
                "This role is on-site at our office.",
                "Hybrid working with flexible hours.",
            ])

        lo, hi = spec["salary"]
        lo, hi = round(lo * pay_factor, -3), round(hi * pay_factor, -3)
        salary_sentence = (
            f"Salary: €{lo:,.0f} - €{hi:,.0f} per year plus 8% holiday allowance."
            if rng.random() < 0.65 else "Competitive salary and a strong benefits package."
        )
        degree = rng.choice(["a Bachelor's degree in Computer Science or a related field",
                             "a Master's degree in a quantitative field", "a relevant degree or equivalent experience"])

        description = (
            f"{company} is looking for a {title} to join our growing data team in {location}.\n\n"
            f"What you will do: build and improve solutions with {', '.join(skills[:3])} and work closely with "
            f"product and business teams.\n\n"
            f"What we ask:\n"
            f"- {years}+ years of experience in a similar role\n"
            f"- Strong hands-on experience with {', '.join(skills)}\n"
            f"- {degree}\n"
            f"- {', '.join(soft).capitalize()}\n\n"
            f"What we offer: {salary_sentence} {mode_sentence}"
        )
        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "url": None,
            "source": "Demo",
            "posted_at": None,
            "applicants": rng.randint(5, 250),
            "experience_level": None,
            "employment_type": "Full-time",
            "work_mode_hint": None,
            "industry": None,
            "salary_min_hint": None,
            "salary_max_hint": None,
            "salary_currency_hint": None,
        })
    return jobs
