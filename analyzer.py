import json
import os

import google.generativeai as genai
import streamlit as st

def configure_genai():
    """Read the Gemini key from Streamlit secrets or the environment.

    The key is looked up BY NAME. Never put the key value itself in this file:
    this repository is public, and anything committed here stays in git history
    even after it is deleted.
    """
    api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error(
            "GEMINI_API_KEY is not set. Add it to .streamlit/secrets.toml "
            "(see .streamlit/secrets.toml.example) or export it in your shell."
        )
        return False
    genai.configure(api_key=api_key)
    return True

def analyze_job_text(text):
    if not configure_genai():
        return None

    generation_config = {
        "temperature": 0.0,
        "response_mime_type": "application/json",
    }
    
    model = genai.GenerativeModel("gemini-1.5-flash", generation_config=generation_config)

    prompt = f"""
    You are a strict data extractor. Analyze the job description below.
    Extract ONLY explicitly stated requirements. Do NOT halllucinate.
    
    Return a JSON object with this exact structure:
    {{
        "skills": ["skill1", "skill2"],
        "tools": ["tool1", "tool2"],
        "years_experience": number (0 if not mentioned),
        "salary_max": number (0 if not mentioned)
    }}

    Job Description:
    {text[:4000]}
    """

    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except json.JSONDecodeError:
        st.warning("The model returned something that was not valid JSON; skipping this posting.")
        return {"skills": [], "tools": [], "years_experience": 0, "salary_max": 0}
    except Exception as exc:
        st.warning(f"Analysis failed for one posting: {exc}")
        return {"skills": [], "tools": [], "years_experience": 0, "salary_max": 0}