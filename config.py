"""Reads API keys from Streamlit secrets or environment variables. Never hard-code keys here."""

import os

import streamlit as st

DEFAULTS = {
    "GEMINI_MODEL": "gemini-flash-latest",
    "APIFY_ACTOR_ID": "bebity/linkedin-jobs-scraper",
}


def get_setting(name):
    """Look up `name` in .streamlit/secrets.toml first, then in environment variables."""
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets.toml at all
        value = None
    return value or os.environ.get(name) or DEFAULTS.get(name)
