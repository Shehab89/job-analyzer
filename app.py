import pandas as pd
import plotly.express as px
import streamlit as st

import insights as ins
import scraper
from analyzer import analyze_jobs
from config import get_setting
from sample_data import load_sample_jobs

st.set_page_config(page_title="Job Market Analyzer", page_icon="🔎", layout="wide")

ACCENT = "#2563eb"
PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]
NEUTRAL = "#9ca3af"
SEQ = ["#dbeafe", "#93c5fd", "#3b82f6", "#1d4ed8", "#1e3a8a"]
px.defaults.color_discrete_sequence = PALETTE


def style(fig, height=380):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), legend_title_text="",
                      hoverlabel=dict(namelength=-1))
    return fig


def show(fig, height=380):
    st.plotly_chart(style(fig, height), width="stretch", config={"displayModeBar": False})


def share_bar(counts, title, top=15, color=ACCENT):
    data = counts.head(top).iloc[::-1]
    fig = px.bar(data, x="Share", y="Item", orientation="h", title=title, text="Share",
                 hover_data={"Jobs": True, "Share": ":.0%", "Item": False})
    fig.update_traces(marker_color=color, texttemplate="%{text:.0%}", textposition="outside", cliponaxis=False)
    fig.update_layout(xaxis_tickformat=".0%", xaxis_title="Share of postings", yaxis_title="")
    return fig


def donut(frame, title):
    fig = px.pie(frame, values="Jobs", names="Category", title=title, hole=0.55)
    colors = [NEUTRAL if c in ("Not stated", "Unknown") else PALETTE[i % len(PALETTE)]
              for i, c in enumerate(frame["Category"])]
    fig.update_traces(textinfo="percent+label", textposition="outside", sort=False, marker_colors=colors)
    fig.update_layout(showlegend=False)
    return fig


# ----------------------------------------------------------------------------- sidebar

gemini_key = get_setting("GEMINI_API_KEY")
apify_token = get_setting("APIFY_API_TOKEN")
adzuna_id, adzuna_key = get_setting("ADZUNA_APP_ID"), get_setting("ADZUNA_APP_KEY")

with st.sidebar:
    st.header("1 · Where to get jobs")
    source = st.radio("Data source", scraper.SOURCES, index=0,
                      help="JobSpy and Demo need no keys. Adzuna needs a free key, Apify a paid token.")
    is_demo = source.startswith("Demo")

    st.header("2 · What to search")
    job_title = st.text_input("Job title", "Data Engineer", disabled=is_demo)
    country = st.selectbox("Country", list(scraper.COUNTRIES), index=0, disabled=is_demo)
    location = st.text_input("City / region (optional)", "", disabled=is_demo,
                             placeholder="e.g. Amsterdam — empty = whole country")
    sites = ["LinkedIn"]
    if source.startswith("JobSpy"):
        sites = st.multiselect("Job sites", list(scraper.JOBSPY_SITES), default=["LinkedIn", "Indeed"])
    date_posted = st.selectbox("Posted", list(scraper.DATE_POSTED_HOURS), index=2, disabled=is_demo)
    max_jobs = st.slider("Jobs per site", 5, 100, 30, step=5, disabled=is_demo)

    st.header("3 · How to analyse")
    use_ai = st.toggle("AI extraction (Gemini)", value=bool(gemini_key), disabled=not gemini_key,
                       help="More accurate. Without a GEMINI_API_KEY the free keyword extractor is used.")
    if not gemini_key:
        st.caption("No `GEMINI_API_KEY` found → using the free keyword extractor.")
    my_skills_text = st.text_area("Your skills (optional, comma separated)", "Python, SQL, Power BI, Azure",
                                  help="Used in the 'Your match' tab to compare you with the market.")

    run = st.button("🚀 Analyze the market", type="primary", width="stretch")

# ----------------------------------------------------------------------------- run pipeline


def fetch_jobs():
    if is_demo:
        return load_sample_jobs()
    if source.startswith("JobSpy"):
        if not sites:
            raise scraper.ScrapeError("Pick at least one job site.")
        return scraper.scrape_jobspy(job_title, location, country, tuple(sites), max_jobs, date_posted)
    if source.startswith("Adzuna"):
        if not (adzuna_id and adzuna_key):
            raise scraper.ScrapeError("Add ADZUNA_APP_ID and ADZUNA_APP_KEY to your secrets "
                                      "(free at https://developer.adzuna.com).")
        return scraper.scrape_adzuna(job_title, location, country, max_jobs, date_posted, adzuna_id, adzuna_key)
    if not apify_token:
        raise scraper.ScrapeError("Add APIFY_API_TOKEN to your secrets to use Apify.")
    where = f"{location}, {country}" if location else country
    return scraper.scrape_apify(job_title, where, max_jobs, date_posted, get_setting("APIFY_ACTOR_ID"), apify_token)


if run:
    with st.status("Collecting job postings…", expanded=True) as status:
        try:
            raw_jobs = fetch_jobs()
        except scraper.ScrapeError as exc:
            status.update(label="Could not collect jobs", state="error")
            st.error(str(exc))
            st.stop()
        if not raw_jobs:
            status.update(label="No jobs found", state="error")
            st.warning("No postings matched. Try a broader title, another location or 'Any time'.")
            st.stop()
        st.write(f"Found **{len(raw_jobs)}** postings. Extracting skills, experience and salary…")
        bar = st.progress(0.0)
        analysed, problems = analyze_jobs(
            raw_jobs, api_key=gemini_key if use_ai else None, model=get_setting("GEMINI_MODEL"),
            on_progress=lambda p: bar.progress(p),
        )
        if problems:
            st.warning(f"AI failed on {len(problems)} posting(s); used the keyword extractor instead. "
                       f"First error: {problems[0]}")
        status.update(label=f"Analysed {len(analysed)} postings", state="complete", expanded=False)
    st.session_state["jobs"] = analysed
    st.session_state["query"] = "Demo data (fictional)" if is_demo else f"{job_title} · {location or country}"

# ----------------------------------------------------------------------------- landing page

st.title("🔎 Job Market Analyzer")

if "jobs" not in st.session_state:
    st.markdown(
        "Find out **what employers really ask for**: the most wanted skills and tools, how much experience "
        "you need, what it pays and who is hiring. Pick a source and a job title on the left and press "
        "**Analyze the market**."
    )
    c1, c2, c3 = st.columns(3)
    c1.info("**1. Collect**\n\nJob postings from LinkedIn, Indeed, Glassdoor, Google Jobs or Adzuna.")
    c2.info("**2. Extract**\n\nAI (or a free keyword engine) reads every posting and pulls out the facts.")
    c3.info("**3. Understand**\n\nCharts, plain-language insights and a match score against your own skills.")
    if st.button("✨ Try it now with demo data (no keys needed)"):
        st.session_state["jobs"], _ = analyze_jobs(load_sample_jobs())
        st.session_state["query"] = "Demo data (fictional)"
        st.rerun()
    st.stop()

# ----------------------------------------------------------------------------- dashboard

df_all = ins.to_frame(st.session_state["jobs"])
st.caption(f"Search: **{st.session_state['query']}** · {len(df_all)} postings · "
           f"extracted by {', '.join(sorted(df_all['extracted_by'].unique()))}")

f1, f2, f3 = st.columns(3)
levels = [lvl for lvl in ins.SENIORITY_LEVELS if lvl in set(df_all["seniority"].dropna())]
sel_levels = f1.multiselect("Filter: seniority", levels, placeholder="All levels")
modes = [m for m in ins.WORK_MODES if m in set(df_all["work_mode"].dropna())]
sel_modes = f2.multiselect("Filter: work mode", modes, placeholder="All work modes")
sel_sources = f3.multiselect("Filter: source", sorted(df_all["source"].dropna().unique()), placeholder="All sources")

df = df_all
if sel_levels:
    df = df[df["seniority"].isin(sel_levels)]
if sel_modes:
    df = df[df["work_mode"].isin(sel_modes)]
if sel_sources:
    df = df[df["source"].isin(sel_sources)]
if df.empty:
    st.warning("No postings match these filters.")
    st.stop()

sal, currency = ins.salary_frame(df)
link_col = ["url"] if df["url"].notna().any() else []  # demo data has no links
tech = ins.count_items(df, "tech_skills")
tools = ins.count_items(df, "tools")

tab_overview, tab_skills, tab_pay, tab_companies, tab_match, tab_jobs = st.tabs(
    ["📊 Overview", "🧠 Skills & tools", "💶 Experience & salary", "🏢 Companies & places", "🎯 Your match",
     "📄 All jobs"])

with tab_overview:
    k = st.columns(5)
    k[0].metric("Postings", len(df))
    k[1].metric("Companies", df["company"].nunique())
    years = df["years_experience"].dropna()
    k[2].metric("Median experience", f"{years.median():.0f} yrs" if not years.empty else "–")
    modes_known = df["work_mode"].dropna()
    k[3].metric("Remote or hybrid", f"{modes_known.isin(['Remote', 'Hybrid']).mean():.0%}" if not modes_known.empty else "–")
    k[4].metric("Median salary", ins.money(sal["salary_mid"].median(), currency) if len(sal) else "–",
                help=f"Yearly, based on the {len(sal)} postings that publish a salary.")

    st.subheader("💡 Key insights")
    for line in ins.key_insights(df) or ["Not enough data for insights yet — try more postings."]:
        st.markdown(f"- {line}")

    c1, c2 = st.columns([3, 2])
    with c1:
        show(share_bar(ins.count_items(df, "all_skills"), "Top 10 skills & tools", top=10))
    with c2:
        show(donut(ins.category_share(df, "seniority", ins.SENIORITY_LEVELS), "Seniority mix"))

with tab_skills:
    c1, c2 = st.columns(2)
    with c1:
        show(share_bar(tech, "Most requested technical skills"), 520)
    with c2:
        show(share_bar(tools, "Most requested tools & platforms", color=PALETTE[1]), 520)

    st.subheader("Which skills go together?")
    st.caption("Number of postings that ask for both skills. The diagonal is how often each skill appears.")
    matrix = ins.cooccurrence(df)
    if len(matrix) >= 2:
        fig = px.imshow(matrix, text_auto=True, color_continuous_scale=SEQ, aspect="auto")
        fig.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="")
        show(fig, 520)

    st.subheader("What each seniority level asks for")
    top_skills = ins.count_items(df, "all_skills", 12)["Item"].tolist()
    lv = [lvl for lvl in ins.SENIORITY_LEVELS if lvl in set(df["seniority"].dropna())]
    if top_skills and len(lv) >= 2:
        grid = pd.DataFrame({level: [df.loc[df["seniority"] == level, "all_skills"].apply(lambda s, k=skill: k in s).mean()
                                     for skill in top_skills] for level in lv}, index=top_skills)
        fig = px.imshow(grid, text_auto=".0%", color_continuous_scale=SEQ, aspect="auto", zmin=0, zmax=1)
        fig.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="")
        show(fig, 480)
    else:
        st.caption("Needs postings from at least two seniority levels.")

    soft = ins.count_items(df, "soft_skills")
    if not soft.empty:
        show(share_bar(soft, "Soft skills & languages", top=8, color=PALETTE[4]), 320)

with tab_pay:
    c1, c2 = st.columns(2)
    with c1:
        if not years.empty:
            fig = px.histogram(years, x="years_experience", nbins=int(min(15, years.max() + 1)),
                               title="Years of experience required")
            fig.update_traces(marker_color=ACCENT)
            fig.update_layout(xaxis_title="Years", yaxis_title="Postings", bargap=0.1)
            show(fig)
            st.caption(f"{len(years)} of {len(df)} postings state a number of years.")
        else:
            st.info("No posting states a number of years of experience.")
    with c2:
        edu = ins.category_share(df, "education", ["Bachelor", "Master", "PhD"])
        show(donut(edu, "Education asked for"))

    st.subheader(f"Salary ({currency or 'n/a'}, yearly)")
    if len(sal) >= 3:
        order = [lvl for lvl in ins.SENIORITY_LEVELS if lvl in set(sal["seniority"].dropna())]
        fig = px.box(sal.dropna(subset=["seniority"]), x="seniority", y="salary_mid", points="all",
                     category_orders={"seniority": order}, color="seniority", title="Salary by seniority",
                     hover_data=["title", "company"])
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title=f"Yearly salary ({currency})")
        show(fig, 420)

        premium, _ = ins.skill_premium(df)
        if not premium.empty:
            fig = px.bar(premium.iloc[::-1], x="Premium", y="Skill", orientation="h", text="Premium",
                         title="Salary premium: postings with vs. without the skill",
                         hover_data={"With skill": ":,.0f", "Without": ":,.0f", "Jobs": True})
            fig.update_traces(texttemplate="%{text:+.0%}", textposition="outside", cliponaxis=False,
                              marker_color=[PALETTE[1] if p > 0 else PALETTE[3] for p in premium.iloc[::-1]["Premium"]])
            fig.update_layout(xaxis_tickformat="+.0%", xaxis_title="Median salary difference", yaxis_title="")
            show(fig, 420)
            st.caption("Correlation, not causation: senior roles list more skills *and* pay more.")
        st.caption(f"Based on {len(sal)} of {len(df)} postings that publish a salary.")
    else:
        st.info("Fewer than 3 postings publish a salary, so there is not enough data for salary charts.")

with tab_companies:
    c1, c2 = st.columns(2)
    with c1:
        comp = df["company"].value_counts().head(15).rename_axis("Company").reset_index(name="Postings")
        fig = px.bar(comp.iloc[::-1], x="Postings", y="Company", orientation="h", title="Who is hiring the most")
        fig.update_traces(marker_color=ACCENT)
        fig.update_layout(yaxis_title="")
        show(fig, 480)
    with c2:
        loc = df["location"].value_counts().head(15).rename_axis("Location").reset_index(name="Postings")
        fig = px.bar(loc.iloc[::-1], x="Postings", y="Location", orientation="h", title="Where the jobs are")
        fig.update_traces(marker_color=PALETTE[1])
        fig.update_layout(yaxis_title="")
        show(fig, 480)
    c3, c4 = st.columns(2)
    with c3:
        show(donut(ins.category_share(df, "work_mode", ins.WORK_MODES), "Remote, hybrid or on-site"))
    with c4:
        src = df["source"].fillna("Unknown").value_counts().rename_axis("Category").reset_index(name="Jobs")
        show(donut(src, "Where the postings came from"))

with tab_match:
    my_skills = [s for s in my_skills_text.split(",") if s.strip()]
    per_job, missing = ins.skill_match(df, my_skills)
    if per_job is None:
        st.info("Type your skills in the sidebar (comma separated) to see how well you match this market.")
    else:
        scores = per_job["Match"].dropna()
        m = st.columns(3)
        m[0].metric("Average match", f"{scores.mean():.0%}" if not scores.empty else "–")
        m[1].metric("Postings where you match ≥ 50%", int((scores >= 0.5).sum()))
        m[2].metric("Your skills recognised", len(my_skills))
        c1, c2 = st.columns(2)
        with c1:
            if not missing.empty:
                show(share_bar(missing, "Top skills you don't list yet (learn these next)", top=8,
                               color=PALETTE[2]), 400)
            else:
                st.success("You already list every top skill in this market. 🎉")
        with c2:
            fig = px.histogram(scores, x="Match", nbins=10, title="How well you match each posting")
            fig.update_traces(marker_color=PALETTE[1])
            fig.update_layout(xaxis_tickformat=".0%", xaxis_title="Share of the posting's skills you have",
                              yaxis_title="Postings", bargap=0.1)
            show(fig, 400)
        st.subheader("Best matching postings")
        best = per_job.dropna(subset=["Match"]).sort_values("Match", ascending=False).head(10)
        best = best.assign(Match=(best["Match"] * 100).round())
        st.dataframe(best[["title", "company", "location", "Match"] + link_col], hide_index=True,
                     column_config={"Match": st.column_config.ProgressColumn("Match", format="%d%%",
                                                                             min_value=0, max_value=100),
                                    "url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
                                    "title": "Title", "company": "Company", "location": "Location"})

with tab_jobs:
    table = df.assign(
        skills=df["all_skills"].apply(", ".join),
        salary=df.apply(lambda r: f"{ins.money(r.salary_min, r.salary_currency)} – "
                                  f"{ins.money(r.salary_max, r.salary_currency)}"
                        if pd.notna(r.salary_min) else "", axis=1),
    )
    cols = ["title", "company", "location", "seniority", "work_mode", "years_experience", "salary", "skills",
            "source"] + link_col
    st.dataframe(table[cols], hide_index=True, height=520,
                 column_config={"url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
                                "years_experience": st.column_config.NumberColumn("Years", format="%.0f"),
                                "title": "Title", "company": "Company", "location": "Location",
                                "seniority": "Seniority", "work_mode": "Work mode", "salary": "Salary",
                                "skills": "Skills & tools", "source": "Source"})
    export = table.drop(columns=["all_skills", "salary"]).copy()
    for col in ins.LIST_COLUMNS:
        export[col] = export[col].apply(", ".join)
    st.download_button("⬇️ Download as CSV", export.to_csv(index=False).encode("utf-8"),
                       file_name="job_market_analysis.csv", mime="text/csv")
