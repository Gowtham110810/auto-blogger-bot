import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "keepupdatedtrend.db"

st.set_page_config(
    page_title="KeepUpdatedTrend Intelligence Terminal",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ KeepUpdatedTrend — Publishing & Intelligence Dashboard")
st.caption("Modular AI Publishing Pipeline: Discover → Research → Create → Validate → Distribute → Learn")

def load_df(query):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

articles_df = load_df("SELECT * FROM articles_catalogue ORDER BY id DESC")
topics_df = load_df("SELECT * FROM topic_queue ORDER BY weighted_total DESC")
claims_df = load_df("SELECT * FROM claim_records ORDER BY id DESC")
metrics_df = load_df("SELECT * FROM article_metrics ORDER BY devto_views DESC")
recs_df = load_df("SELECT * FROM weekly_recommendations ORDER BY id DESC")

# Top KPI Row
col1, col2, col3, col4 = st.columns(4)
col1.metric("Published Articles", len(articles_df))
avg_score = round(topics_df["weighted_total"].mean(), 1) if not topics_df.empty else 0
col2.metric("Avg Topic Score", f"{avg_score} / 100")
verified_cnt = len(claims_df[claims_df["verification_status"] == "verified"]) if not claims_df.empty else 0
col3.metric("Verified Claims", f"{verified_cnt} / {len(claims_df)}")
total_devto_views = int(metrics_df["devto_views"].sum()) if not metrics_df.empty else 0
col4.metric("Syndicated Dev.to Views", total_devto_views)

st.divider()

# Weekly Feedback Recommendations
st.subheader("🧭 Weekly Optimization & Feedback Rules")
if not recs_df.empty:
    st.dataframe(recs_df[["rule_triggered", "target_item", "recommendation", "created_at"]], use_container_width=True)
else:
    st.info("Run analytics_engine.py to populate weekly optimization recommendations.")

# Published Catalogue & Topic Queue
left_col, right_col = st.columns(2)
with left_col:
    st.subheader("📚 Published Articles Catalogue")
    if not articles_df.empty:
        st.dataframe(articles_df[["title", "pillar", "primary_keyword", "publish_state", "url"]], use_container_width=True)
    else:
        st.write("No articles recorded in SQLite yet.")

with right_col:
    st.subheader("🎯 Scored Topic Intelligence Queue")
    if not topics_df.empty:
        st.dataframe(topics_df[["primary_keyword", "pillar", "weighted_total", "status", "reader_question"]], use_container_width=True)
    else:
        st.write("No topics queued yet.")

# Fact-Checking & Claims Ledger
st.subheader("🔎 Fact-Checking & Source Verification Ledger")
if not claims_df.empty:
    st.dataframe(claims_df[["claim", "source", "verification_status", "confidence", "source_url"]], use_container_width=True)
else:
    st.write("No claim records logged yet.")

# Roadmap Revenue Scenario Calculator
st.subheader("💰 Ad Revenue Scenario Simulator (Illustrative)")
p_col1, p_col2, p_col3 = st.columns(3)
monthly_views = p_col1.number_input("Projected Monthly Pageviews", min_value=100, value=10000, step=1000)
assumed_rpm = p_col2.number_input("Assumed Page RPM ($)", min_value=1.0, value=10.0, step=1.0)
est_rev = (monthly_views * assumed_rpm) / 1000.0
p_col3.metric("Illustrative Monthly Revenue", f"${est_rev:,.2f}")
