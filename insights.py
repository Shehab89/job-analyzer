"""Pure pandas: turns the analysed jobs into tables and plain-language insights. No Streamlit here."""

from itertools import combinations

import pandas as pd

import skills_catalog as catalog
from analyzer import SENIORITY_LEVELS, WORK_MODES

LIST_COLUMNS = ["tech_skills", "tools", "soft_skills"]


def to_frame(jobs):
    df = pd.DataFrame(jobs)
    for col in LIST_COLUMNS:
        if col not in df:
            df[col] = [[] for _ in range(len(df))]
        df[col] = df[col].apply(lambda v: v if isinstance(v, list) else [])
    df["all_skills"] = df["tech_skills"] + df["tools"]
    for col in ["years_experience", "salary_min", "salary_max"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["salary_mid"] = (df["salary_min"] + df["salary_max"]) / 2
    return df


def count_items(df, column, top=None):
    """How many postings mention each item, and what share of all postings that is."""
    exploded = df[column].explode().dropna()
    if exploded.empty:
        return pd.DataFrame(columns=["Item", "Jobs", "Share"])
    counts = exploded.value_counts().rename_axis("Item").reset_index(name="Jobs")
    counts["Share"] = counts["Jobs"] / len(df)
    return counts.head(top) if top else counts


def category_share(df, column, order):
    counts = df[column].fillna("Not stated").value_counts()
    labels = [x for x in order if x in counts] + (["Not stated"] if "Not stated" in counts else [])
    return pd.DataFrame({"Category": labels, "Jobs": [int(counts[x]) for x in labels]})


def cooccurrence(df, column="all_skills", top=12):
    """Matrix of how often the top skills are asked for together in the same posting."""
    top_items = count_items(df, column, top)["Item"].tolist()
    matrix = pd.DataFrame(0, index=top_items, columns=top_items)
    for items in df[column]:
        present = [i for i in top_items if i in items]
        for i in present:
            matrix.loc[i, i] += 1
        for a, b in combinations(present, 2):
            matrix.loc[a, b] += 1
            matrix.loc[b, a] += 1
    return matrix


def main_currency(df):
    cur = df.loc[df["salary_mid"].notna(), "salary_currency"].dropna()
    return cur.mode().iloc[0] if not cur.empty else None


def salary_frame(df):
    """Only postings with a yearly salary in the most common currency, so numbers are comparable."""
    currency = main_currency(df)
    if not currency:
        return df.iloc[0:0], None
    return df[df["salary_mid"].notna() & (df["salary_currency"] == currency)], currency


def skill_premium(df, min_jobs=3, top=10):
    """Median salary of postings that ask for a skill vs. those that don't."""
    sal, currency = salary_frame(df)
    if len(sal) < 2 * min_jobs:
        return pd.DataFrame(), currency
    rows = []
    for skill in count_items(sal, "all_skills")["Item"]:
        has = sal["all_skills"].apply(lambda s: skill in s)
        if has.sum() >= min_jobs and (~has).sum() >= min_jobs:
            with_s, without = sal.loc[has, "salary_mid"].median(), sal.loc[~has, "salary_mid"].median()
            rows.append({"Skill": skill, "With skill": with_s, "Without": without,
                         "Premium": (with_s - without) / without, "Jobs": int(has.sum())})
    out = pd.DataFrame(rows)
    if out.empty:
        return out, currency
    return out.sort_values("Premium", ascending=False).head(top), currency


def money(value, currency):
    symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, (currency or "") + " ")
    return f"{symbol}{value / 1000:,.0f}k"


def key_insights(df):
    """A handful of short, plain-English takeaways computed from the data."""
    n = len(df)
    out = []
    skills = count_items(df, "tech_skills", 3)
    if not skills.empty:
        top = skills.iloc[0]
        out.append(f"**{top['Item']}** is the most requested skill: it appears in **{top['Share']:.0%}** of postings.")
        if len(skills) >= 3:
            out.append(f"The core skill trio is **{skills['Item'].iloc[0]}**, **{skills['Item'].iloc[1]}** "
                       f"and **{skills['Item'].iloc[2]}**.")
    tools = count_items(df, "tools", 1)
    if not tools.empty:
        out.append(f"Top tool: **{tools.iloc[0]['Item']}** ({tools.iloc[0]['Share']:.0%} of postings).")

    years = df["years_experience"].dropna()
    if not years.empty:
        entry = (years <= 2).mean()
        out.append(f"Median experience asked is **{years.median():.0f} years**; "
                   f"**{entry:.0%}** of postings that mention it accept 2 years or less.")

    modes = df["work_mode"].dropna()
    if not modes.empty:
        flexible = modes.isin(["Remote", "Hybrid"]).mean()
        out.append(f"**{flexible:.0%}** of postings that state a work mode are remote or hybrid.")

    sal, currency = salary_frame(df)
    if len(sal) >= 3:
        out.append(f"Typical salary is **{money(sal['salary_mid'].median(), currency)}** a year "
                   f"(range {money(sal['salary_min'].min(), currency)} – {money(sal['salary_max'].max(), currency)}), "
                   f"but only **{len(sal) / n:.0%}** of postings publish a salary.")
    premium, currency = skill_premium(df)
    if not premium.empty and premium.iloc[0]["Premium"] > 0.03:
        p = premium.iloc[0]
        out.append(f"Postings asking for **{p['Skill']}** pay about **{p['Premium']:.0%} more** "
                   f"(median {money(p['With skill'], currency)} vs {money(p['Without'], currency)}).")

    companies = df["company"].value_counts()
    if not companies.empty and companies.iloc[0] > 1:
        out.append(f"Most active hirer: **{companies.index[0]}** with **{companies.iloc[0]}** open roles.")
    return out


def skill_match(df, my_skills):
    """Compare the user's skills with the market. Returns (coverage table, missing top skills)."""
    mine = {catalog.normalize(s).lower() for s in my_skills if s.strip()}
    if not mine or df.empty:
        return None, pd.DataFrame()

    def coverage(items):
        return len({i.lower() for i in items} & mine) / len(items) if items else None

    per_job = df.assign(Match=df["all_skills"].apply(coverage))
    market = count_items(df, "all_skills", 15)
    missing = market[~market["Item"].str.lower().isin(mine)]
    return per_job, missing


__all__ = ["to_frame", "count_items", "category_share", "cooccurrence", "salary_frame", "skill_premium",
           "key_insights", "skill_match", "money", "SENIORITY_LEVELS", "WORK_MODES"]
