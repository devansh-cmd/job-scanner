"""Job Scanner dashboard (Streamlit).

Run locally:   streamlit run dashboard/app.py
Secrets (Streamlit Cloud > App settings > Secrets, or .streamlit/secrets.toml):
    SUPABASE_DB_URL = "postgresql://..."     # Session pooler string
    DASHBOARD_PASSWORD = "..."               # optional but recommended
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobscan import db  # noqa: E402

st.set_page_config(page_title="Job Scanner", page_icon="🎯", layout="wide")


def secret(name: str) -> str | None:
    try:
        if name in st.secrets:
            return st.secrets[name]
    except FileNotFoundError:
        pass
    return os.environ.get(name)


# ---------- password gate ----------
password = secret("DASHBOARD_PASSWORD")
if password and not st.session_state.get("authed"):
    st.title("Job Scanner")
    entered = st.text_input("Password", type="password")
    if entered:
        if entered == password:
            st.session_state.authed = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()

DB_URL = secret("SUPABASE_DB_URL")
if not DB_URL:
    st.error("SUPABASE_DB_URL is not set. Add it in the app's Secrets.")
    st.stop()

BUCKET_LABEL = {"strong": "Strong", "check_manually": "Check", "drop": "Dropped"}
ROLE_LABEL = {"swe_ai_ml": "SWE / AI-ML", "product_management": "Product", "tech_consulting": "Consulting",
              "quant_dev": "Quant dev", "data_science": "Data science", "tech_risk": "Tech risk", "other": "Other"}


@st.cache_data(ttl=120, show_spinner="Loading jobs...")
def load_jobs(days: int) -> pd.DataFrame:
    with db.connect(DB_URL) as conn:
        db.init(conn)
        rows = db.load(conn, days)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["first_seen"] = pd.to_datetime(df["first_seen"])
    df["Seen"] = df["first_seen"].dt.strftime("%d %b")
    df["Bucket"] = df["bucket"].map(BUCKET_LABEL).fillna(df["bucket"])
    df["Role"] = df["role_family"].map(ROLE_LABEL).fillna("Other")
    df["Board"] = df["source"].str.replace("_alert", "", regex=False).str.split(":").str[0]
    df["Sponsor"] = df.apply(
        lambda r: "Register" if r["on_register"] else
        (f"{r['sponsorship_p']:.0%}" if pd.notna(r["sponsorship_p"]) else ""), axis=1)
    return df


# ---------- sidebar filters ----------
with st.sidebar:
    st.header("Filters")
    days = st.select_slider("Seen in the last", options=[1, 3, 7, 14, 30, 90], value=14,
                            format_func=lambda d: f"{d} day" + ("s" if d > 1 else ""))
    buckets = st.multiselect("Bucket", ["Strong", "Check", "Dropped"], default=["Strong", "Check"])
    statuses = st.multiselect("Status", db.STATUSES,
                              default=[s for s in db.STATUSES if s not in ("hidden", "rejected")])
    roles = st.multiselect("Role", list(ROLE_LABEL.values()), default=list(ROLE_LABEL.values()))
    query = st.text_input("Search title or company")
    if st.button("Refresh data"):
        load_jobs.clear()
        st.rerun()

df = load_jobs(days)

st.title("Job Scanner")
if df.empty:
    st.info("No jobs yet in this window. They appear after the next daily run.")
    st.stop()

# ---------- headline numbers ----------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Strong, untouched", int(((df.bucket == "strong") & (df.status == "new")).sum()))
c2.metric("To check, untouched", int(((df.bucket == "check_manually") & (df.status == "new")).sum()))
c3.metric("Applied", int((df.status == "applied").sum()))
c4.metric("Interviewing", int((df.status == "interviewing").sum()))
c5.metric("Offers", int((df.status == "offer").sum()))
st.caption(f"Counts cover jobs first seen in the last {days} days.")

triage, tracker = st.tabs(["Triage", "Applications"])

# ---------- triage ----------
with triage:
    view = df[df["Bucket"].isin(buckets) & df["status"].isin(statuses) & df["Role"].isin(roles)]
    if query:
        q = query.lower()
        view = view[view["title"].str.lower().str.contains(q, regex=False)
                    | view["company"].str.lower().str.contains(q, regex=False)]
    st.write(f"**{len(view)}** jobs. Change Status or Notes, then press Save.")

    # Editable columns first, so they never sit off-screen
    cols = ["id", "status", "title", "company", "url", "profile_match", "Sponsor", "Bucket",
            "Role", "location", "Seen", "Board", "notes", "reasons"]
    edited = st.data_editor(
        view[cols].reset_index(drop=True),
        key="editor", hide_index=True, use_container_width=True, height=560,
        disabled=[c for c in cols if c not in ("status", "notes")],
        column_order=[c for c in cols if c != "id"],
        column_config={
            "title": st.column_config.TextColumn("Title", width="large"),
            "company": "Company",
            "location": "Location",
            "profile_match": st.column_config.NumberColumn("Match", format="%d/5"),
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
            "reasons": st.column_config.TextColumn("Why", width="medium"),
            "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES, required=True),
            "notes": st.column_config.TextColumn("Notes", width="medium"),
        },
    )

    original = view[["id", "status", "notes"]].reset_index(drop=True)
    changed = edited[(edited["status"] != original["status"]) | (edited["notes"] != original["notes"])]
    if st.button(f"Save {len(changed)} change(s)", type="primary", disabled=changed.empty):
        with db.connect(DB_URL) as conn:
            for _, r in changed.iterrows():
                db.update(conn, r["id"], r["status"], r["notes"] or "")
        load_jobs.clear()
        st.toast(f"Saved {len(changed)} change(s)")
        st.rerun()

# ---------- application tracker ----------
with tracker:
    active = df[df["status"].isin(["interested", "applied", "interviewing", "offer", "rejected"])]
    counts = active["status"].value_counts()
    cols = st.columns(5)
    for col, s in zip(cols, ["interested", "applied", "interviewing", "offer", "rejected"]):
        col.metric(s.capitalize(), int(counts.get(s, 0)))
    if active.empty:
        st.info("Mark jobs as interested or applied in Triage and they show up here.")
    else:
        st.dataframe(
            active.sort_values("status_updated_at", ascending=False)[
                ["status", "title", "company", "Role", "Board", "status_updated_at", "notes", "url"]],
            hide_index=True, use_container_width=True,
            column_config={
                "status": "Status", "title": "Title", "company": "Company",
                "status_updated_at": st.column_config.DatetimeColumn("Updated", format="D MMM, HH:mm"),
                "notes": "Notes", "url": st.column_config.LinkColumn("Link", display_text="Open"),
            })
