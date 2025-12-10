from apify_client import ApifyClient
import streamlit as st

def get_apify_client():
  
    token = st.secrets.get("apify_api_cIVfOFq8agM5ctMITBGbXOUL5ujRbU0tzB6x")
    if not token:
        return None
    return ApifyClient(token)

def scrape_linkedin(job_title, location, max_jobs=10):
    client = get_apify_client()
    if not client:
        st.error("Apify API Token not found!")
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