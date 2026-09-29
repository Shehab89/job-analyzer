"""Known skills and tools, with aliases, so the same thing is always counted under one name.

Used in two places:
  * the offline extractor (keyword matching when no AI key is configured)
  * normalising whatever the AI returns ("py", "Python 3" -> "Python")
"""

import re

# canonical name -> aliases (lower-case). The canonical name itself is matched too.
TECH_SKILLS = {
    "Python": ["python3", "python 3"],
    "SQL": ["t-sql", "tsql", "pl/sql", "plsql"],
    "Java": [],
    "JavaScript": ["js", "ecmascript"],
    "TypeScript": [],
    "C#": ["c sharp", "csharp"],
    "C++": ["cpp"],
    "Go": ["golang"],
    "Rust": [],
    "R": [],
    "Scala": [],
    "Machine Learning": ["ml", "machine-learning"],
    "Deep Learning": ["deep-learning"],
    "NLP": ["natural language processing"],
    "Computer Vision": [],
    "Generative AI": ["genai", "gen ai", "llm", "llms", "large language models"],
    "Data Analysis": ["data analytics", "analytics"],
    "Data Modeling": ["data modelling", "dimensional modeling", "dimensional modelling"],
    "Data Engineering": [],
    "ETL": ["elt", "etl/elt", "data pipelines", "data pipeline"],
    "Statistics": ["statistical analysis", "statistical modeling"],
    "Data Visualization": ["data visualisation", "visualization", "visualisation"],
    "REST APIs": ["REST", "restful", "rest api", "apis", "api design"],
    "Microservices": [],
    "CI/CD": ["ci / cd", "continuous integration", "continuous delivery"],
    "DevOps": [],
    "Cloud Computing": ["cloud"],
    "Testing": ["unit testing", "test automation", "tdd"],
    "System Design": ["software architecture", "distributed systems"],
    "Agile": ["scrum", "kanban"],
    "Security": ["cybersecurity", "application security"],
    "HTML/CSS": ["html", "css", "html5", "css3"],
}

TOOLS = {
    "AWS": ["amazon web services"],
    "Azure": ["microsoft azure"],
    "GCP": ["google cloud", "google cloud platform"],
    "Docker": [],
    "Kubernetes": ["k8s"],
    "Terraform": [],
    "Git": ["github", "gitlab"],
    "Linux": [],
    "Spark": ["pyspark", "apache spark"],
    "Kafka": ["apache kafka"],
    "Airflow": ["apache airflow"],
    "dbt": [],
    "Databricks": [],
    "Snowflake": [],
    "BigQuery": [],
    "PostgreSQL": ["postgres"],
    "MySQL": [],
    "MongoDB": [],
    "Redis": [],
    "Pandas": [],
    "NumPy": [],
    "scikit-learn": ["sklearn", "scikit learn"],
    "TensorFlow": [],
    "PyTorch": [],
    "Power BI": ["powerbi"],
    "Tableau": [],
    "Excel": ["ms excel", "microsoft excel"],
    "Django": [],
    "Flask": [],
    "FastAPI": [],
    "React": ["react.js", "reactjs"],
    "Node.js": ["nodejs"],
    "Angular": [],
    "Vue": ["vue.js", "vuejs"],
    ".NET": ["dotnet", "asp.net"],
    "Spring": ["spring boot"],
    "Jira": [],
    "Figma": [],
}

SOFT_SKILLS = {
    "Communication": ["communication skills", "communicator"],
    "Teamwork": ["team player", "collaboration", "collaborative"],
    "Problem Solving": ["problem-solving", "analytical thinking", "problem solver"],
    "Leadership": ["mentoring", "mentorship"],
    "Stakeholder Management": ["stakeholders"],
    "Ownership": ["self-starter", "proactive", "independent"],
    "English": ["fluent english", "english speaking"],
}

# Ambiguous short names that would match normal words. Only count them when written
# exactly in this case (e.g. "Go", "R") and not at the start of a sentence-ish context.
CASE_SENSITIVE = {"Go", "R", "REST", "js", "cloud", "analytics", "visualization",
                  "visualisation", "independent", "proactive", "stakeholders", "apis"}


def _build(catalog):
    patterns = []
    lookup = {}
    for canonical, aliases in catalog.items():
        for term in [canonical, *aliases]:
            lookup[term.lower()] = canonical
            flags = 0 if term in CASE_SENSITIVE else re.IGNORECASE
            # Word-ish boundaries that also work for names like "C++", "C#", ".NET", "CI/CD".
            pat = re.compile(r"(?<![\w+#.&])" + re.escape(term) + r"(?![\w+#&])", flags)
            patterns.append((pat, canonical))
    return patterns, lookup


_TECH_PATTERNS, _TECH_LOOKUP = _build(TECH_SKILLS)
_TOOL_PATTERNS, _TOOL_LOOKUP = _build(TOOLS)
_SOFT_PATTERNS, _SOFT_LOOKUP = _build(SOFT_SKILLS)


def _find(text, patterns):
    found = []
    for pat, canonical in patterns:
        if canonical not in found and pat.search(text):
            found.append(canonical)
    return found


def find_tech_skills(text):
    return _find(text, _TECH_PATTERNS)


def find_tools(text):
    return _find(text, _TOOL_PATTERNS)


def find_soft_skills(text):
    return _find(text, _SOFT_PATTERNS)


def normalize(name):
    """Map a free-text skill/tool name onto its canonical spelling (or tidy it up)."""
    if not name:
        return ""
    clean = re.sub(r"\s+", " ", str(name)).strip(" .,;:-")
    key = clean.lower()
    for lookup in (_TOOL_LOOKUP, _TECH_LOOKUP, _SOFT_LOOKUP):
        if key in lookup:
            return lookup[key]
    # Unknown term: keep acronyms as they are, otherwise Title Case the first letter.
    if clean.isupper() or any(c.isupper() for c in clean[1:]):
        return clean
    return clean[:1].upper() + clean[1:]
