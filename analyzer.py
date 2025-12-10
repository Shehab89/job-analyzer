import google.generativeai as genai
import streamlit as st
import json

def configure_genai():
    api_key = st.secrets.get("AIzaSyCL5yH8nVc4UTRa4PbeXx7dSfSFWVuwqdY")
    if api_key:
        genai.configure(api_key=api_key)
        return True
    return False

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
    except Exception as e:
        return {"skills": [], "tools": [], "years_experience": 0, "salary_max": 0}