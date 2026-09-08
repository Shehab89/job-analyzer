import os

import streamlit as st
from apify_client import ApifyClient

def get_apify_client():
    """Read the Apify token from Streamlit secrets or the environment.

    Looked up BY NAME -- the token value must never appear in this file.
    """
    token = st.secrets.get("APIFY_API_TOKEN") or os.getenv("APIFY_API_TOKEN")
    if not token:
        return None
    return ApifyClient(token)

def scrape_linkedin(job_title, location, max_jobs=10):
    client = get_apify_client()
    if not client:
        st.error(
            "APIFY_API_TOKEN is not set. Add it to .streamlit/secrets.toml "
            "(see .streamlit/secrets.toml.example)."
        )
        return []

    run_input = {
        "keywords": job_title,
        "location": location,
        "limit": max_jobs,
        "datePosted": "pastMonth", 
    }
    
    try:
        run = client.actor("bebity/linkedin-jobs-scraper").call(run_input=run_input)
        dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items
        return dataset_items
    
    except Exception as e:
        st.error(f"Scraping Error: {e}")
        return []