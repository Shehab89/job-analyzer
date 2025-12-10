import streamlit as st
import pandas as pd
import plotly.express as px
from scraper import scrape_linkedin
from analyzer import analyze_job_text


st.set_page_config(page_title="Job Market AI Analyst", layout="wide")

st.title("🔎 AI Job Market Analyzer")
st.markdown("Find a job and artificial intelligence will analyze the market for you.")

with st.sidebar:
    st.header("Search Settings")
    job_title = st.text_input("Job title", "Python Developer")
    location = st.text_input("Location", "Remote")
    max_jobs = st.slider("Number of positions", 2, 20, 5) 
    
    st.info("Note: Make sure to put the keys in Secrets when publishing.")
    
    start_btn = st.button("Analyzing...🚀")

if start_btn:
    
    with st.status("Data Scraping from LinkedIn...", expanded=True) as status:
        st.write("Start connection to Apify...")
        raw_jobs = scrape_linkedin(job_title, location, max_jobs)
        
        if not raw_jobs:
            status.update(label="Failure!", state="error")
            st.stop()
            
        status.update(label=f"Scraped {len(raw_jobs)} Jobs Succefully", state="complete")

    # 2. مرحلة التحليل (AI Analysis)
    st.divider()
    progress_bar = st.progress(0, text="Analyzing job descriptions with AI...")
    
    analyzed_data = []
    
    for i, job in enumerate(raw_jobs):
        full_text = f"{job.get('title', '')} \n {job.get('description', '')}"
        
        if len(full_text) > 50:
            result = analyze_job_text(full_text)
            if result:
                analyzed_data.append(result)
        
        progress_bar.progress((i + 1) / len(raw_jobs))
    
    progress_bar.empty()

    
    if analyzed_data:
       
        all_skills = [s for d in analyzed_data for s in d['skills']]
        all_tools = [t for d in analyzed_data for t in d['tools']]
        
        df_skills = pd.Series(all_skills).value_counts().reset_index()
        df_skills.columns = ["Skill", "Count"]
        
        df_tools = pd.Series(all_tools).value_counts().reset_index()
        df_tools.columns = ["Tool", "Count"]

        # الأعمدة
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔥 The most required skills")
            fig = px.bar(df_skills.head(10), x="Count", y="Skill", orientation='h', title="Top Skills")
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.subheader("🛠 Tools and Technologies")
            fig2 = px.pie(df_tools.head(10), values="Count", names="Tool", title="Top Tools")
            st.plotly_chart(fig2, use_container_width=True)

        
        avg_exp = sum(d['years_experience'] for d in analyzed_data) / len(analyzed_data)
        st.metric("Average experience years", f"{avg_exp:.1f} Years")
        
    else:
        st.warning("No analyzed data available.")