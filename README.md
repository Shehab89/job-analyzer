# Job Market Analyzer

Scrapes LinkedIn job postings for a given title and location, extracts the
skills, tools, experience and salary each posting actually asks for, and
aggregates them into a picture of what a job market currently wants.

Built while researching the Dutch data-engineering market for my own job search —
reading fifty job ads by hand is slow and your impression of them is unreliable.

## What it does

1. **Scrape** — Apify's LinkedIn jobs actor pulls postings for a title/location
2. **Extract** — Gemini reads each description and returns strict JSON: skills,
   tools, years of experience, salary ceiling. Temperature 0 and an explicit
   "extract only what is stated" instruction, because a model that infers
   requirements produces a market picture of its own imagination
3. **Aggregate** — Streamlit charts the most-requested skills and tools and the
   average experience demanded

## Running it

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add your keys
streamlit run app.py
```

You need two free API keys:

- **Gemini** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- **Apify** — [console.apify.com](https://console.apify.com) (the LinkedIn actor is paid per run)

## Configuration

Both credentials are read by name from `st.secrets`, falling back to environment
variables:

| Name | Purpose |
|---|---|
| `GEMINI_API_KEY` | Job-description extraction |
| `APIFY_API_TOKEN` | LinkedIn scraping |

`.streamlit/secrets.toml` is gitignored. Nothing secret belongs in source.

## Known limitations

- Apify's LinkedIn actor charges per run, so `max_jobs` is worth keeping low
- Extraction quality depends on how specific the posting is; vague ads produce
  vague results, which is itself a finding
- No caching yet — re-running the same search re-scrapes and re-analyses

## License

MIT
