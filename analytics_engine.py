import os
import sqlite3
import requests
from datetime import datetime, timezone

DB_PATH = "keepupdatedtrend.db"
DEVTO_API_KEY = os.environ.get("DEVTO_API_KEY", "").strip()

def init_analytics_tables():
    """Creates SQLite tables for performance tracking and weekly feedback rules."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS article_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT UNIQUE,
            pillar TEXT,
            devto_views INTEGER DEFAULT 0,
            devto_reactions INTEGER DEFAULT 0,
            devto_comments INTEGER DEFAULT 0,
            last_synced TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS weekly_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_triggered TEXT,
            target_item TEXT,
            recommendation TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def sync_devto_analytics():
    """Fetches real views, reactions, and engagement from Dev.to API."""
    init_analytics_tables()
    if not DEVTO_API_KEY:
        return

    try:
        resp = requests.get(
            "https://dev.to/api/articles/me/published?per_page=30",
            headers={"api-key": DEVTO_API_KEY},
            timeout=15
        )
        if resp.status_code != 200:
            return
        articles = resp.json()
    except Exception as e:
        print(f"[analytics_engine] Dev.to sync skipped: {e}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    for a in articles:
        canonical = a.get("canonical_url") or a.get("url", "")
        title = a.get("title", "")
        views = int(a.get("page_views_count", 0))
        reactions = int(a.get("positive_reactions_count", 0))
        comments = int(a.get("comments_count", 0))

        cur.execute("""
            INSERT INTO article_metrics (title, url, pillar, devto_views, devto_reactions, devto_comments, last_synced)
            VALUES (?, ?, 'Synced', ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                devto_views = excluded.devto_views,
                devto_reactions = excluded.devto_reactions,
                devto_comments = excluded.devto_comments,
                last_synced = excluded.last_synced
        """, (title, canonical, views, reactions, comments, now))

    conn.commit()
    conn.close()

def generate_weekly_feedback():
    """Applies the roadmap's weekly feedback rules to surface content opportunities."""
    init_analytics_tables()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cur.execute("DELETE FROM weekly_recommendations")

    # Rule 1: Strong topic cluster detection
    cur.execute("""
        SELECT pillar, COUNT(*), AVG(weighted_total)
        FROM topic_queue
        WHERE status = 'published'
        GROUP BY pillar
        ORDER BY AVG(weighted_total) DESC
        LIMIT 1
    """)
    top_cluster = cur.fetchone()
    if top_cluster and top_cluster[0]:
        cur.execute("""
            INSERT INTO weekly_recommendations (rule_triggered, target_item, recommendation, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            "Strong Topic Cluster",
            top_cluster[0],
            f"Pillar '{top_cluster[0]}' has the highest average intelligence score ({round(top_cluster[2], 1)}). Prioritize supporting sub-questions in this cluster.",
            now
        ))

    # Rule 2: Flag unverified or pending claims for human review
    cur.execute("SELECT COUNT(*) FROM claim_records WHERE verification_status != 'verified'")
    unverified_count = cur.fetchone()[0]
    if unverified_count > 0:
        cur.execute("""
            INSERT INTO weekly_recommendations (rule_triggered, target_item, recommendation, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            "Verification Gate Alert",
            f"{unverified_count} Claims Pending",
            "Inspect unverified claims in claim_records before scaling article volume.",
            now
        ))

    # Rule 3: Missing pillar coverage check
    cur.execute("SELECT DISTINCT pillar FROM articles_catalogue WHERE publish_state = 'LIVE'")
    active_pillars = {r[0] for r in cur.fetchall() if r[0]}
    all_pillars = {"Enterprise AI", "FinTech", "ETFs and Investing", "Cloud SaaS", "Financial Technology"}
    missing = all_pillars - active_pillars
    if missing:
        missing_str = ", ".join(sorted(missing))
        cur.execute("""
            INSERT INTO weekly_recommendations (rule_triggered, target_item, recommendation, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            "Pillar Coverage Gap",
            missing_str,
            f"Expand topic discovery into uncovered pillars ({missing_str}) to build balanced topical authority.",
            now
        ))

    conn.commit()
    conn.close()

def run_analytics_cycle():
    sync_devto_analytics()
    generate_weekly_feedback()
    print("[analytics_engine] Analytics sync & weekly feedback rules completed.")

if __name__ == "__main__":
    run_analytics_cycle()
