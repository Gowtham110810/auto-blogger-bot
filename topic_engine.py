import os
import re
import json
import sqlite3
import urllib.parse
import requests
import feedparser
from datetime import datetime, timezone
from google import genai
from google.genai import types

DB_PATH = "keepupdatedtrend.db"

CONTENT_PILLARS = [
    "Enterprise AI",
    "FinTech",
    "ETFs and Investing",
    "Cloud SaaS",
    "Financial Technology"
]

DISCOVERY_FEEDS = [
    "https://trends.google.com/trending/rss?geo=US",
    "https://news.google.com/rss/search?q=Enterprise+AI+Agents+Automation+Security+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=FinTech+Payment+Infrastructure+Digital+Banking+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=ETF+Comparison+Market+Structure+Institutional+Investing+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Cloud+SaaS+Infrastructure+Software+Economics+when:1d&hl=en-US&gl=US&ceid=US:en"
]

def init_db():
    """Initializes the shared SQLite tables for the 7-layer architecture."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Research Queue & Scored Topics
    cur.execute("""
        CREATE TABLE IF NOT EXISTS topic_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            headline TEXT,
            primary_keyword TEXT UNIQUE,
            pillar TEXT,
            reader_question TEXT,
            search_demand_score INTEGER,
            trend_momentum_score INTEGER,
            audience_relevance_score INTEGER,
            monetization_score INTEGER,
            competition_score INTEGER,
            source_reliability_score INTEGER,
            weighted_total REAL,
            status TEXT DEFAULT 'queued',
            created_at TEXT
        )
    """)

    # 2. Published & Draft Articles Catalogue (for SEO Internal Linking)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles_catalogue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT UNIQUE,
            slug TEXT,
            pillar TEXT,
            primary_keyword TEXT,
            publish_state TEXT,
            published_at TEXT
        )
    """)

    # 3. Claims & Fact-Checking Ledger
    cur.execute("""
        CREATE TABLE IF NOT EXISTS claim_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            claim TEXT,
            source TEXT,
            source_url TEXT,
            verification_status TEXT DEFAULT 'pending',
            confidence INTEGER DEFAULT 0,
            checked_at TEXT
        )
    """)

    # 4. Run History & Gate Logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS run_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage TEXT,
            status TEXT,
            details TEXT,
            logged_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def fetch_gdelt_signals(query="enterprise AI OR fintech OR cloud SaaS"):
    """Queries the GDELT 2.0 Doc API for emerging global news events."""
    try:
        encoded = urllib.parse.quote(f"({query}) sourcelang:english")
        url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={encoded}&mode=artlist&maxrecords=8&format=json"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            return [
                {"headline": a.get("title", "").strip(), "source": a.get("domain", "GDELT")}
                for a in articles if a.get("title")
            ]
    except Exception:
        pass
    return []

def fetch_autocomplete(seed):
    """Fetches real search queries from Google US Autocomplete."""
    try:
        encoded = urllib.parse.quote(seed)
        url = f"http://suggestqueries.google.com/complete/search?client=firefox&gl=us&hl=en&q={encoded}"
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            return data[1][:4] if len(data) > 1 else []
    except Exception:
        pass
    return []

def collect_candidates(existing_titles=None):
    """Collects, normalizes, and deduplicates candidate topics across RSS, Trends, and GDELT."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT LOWER(title), LOWER(primary_keyword) FROM articles_catalogue")
    db_rows = cur.fetchall()
    cur.execute("SELECT LOWER(headline), LOWER(primary_keyword) FROM topic_queue")
    queue_rows = cur.fetchall()
    conn.close()

    seen = {t.lower() for t in (existing_titles or [])}
    for r in db_rows + queue_rows:
        if r[0]: seen.add(r[0])
        if r[1]: seen.add(r[1])

    raw_items = []
    for feed_url in DISCOVERY_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:5]:
            clean_title = entry.title.rsplit(" - ", 1)[0].strip()
            raw_items.append({
                "headline": clean_title,
                "source": entry.get("source", {}).get("title", "Google Trends / RSS")
            })

    raw_items.extend(fetch_gdelt_signals())

    unique_candidates = []
    for item in raw_items:
        h_low = item["headline"].lower()
        if len(h_low) < 15 or any(h_low[:22] in s for s in seen):
            continue
        seen.add(h_low[:22])
        words = re.findall(r"[A-Za-z0-9&]+", item["headline"])
        item["autocomplete_queries"] = fetch_autocomplete(" ".join(words[:4]))
        unique_candidates.append(item)
        if len(unique_candidates) >= 12:
            break

    return unique_candidates

def score_and_queue_topics(existing_titles=None):
    """Scores candidates using the roadmap's 6-factor weighted model and queues the best."""
    candidates = collect_candidates(existing_titles)
    if not candidates:
        return None

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(api_version="v1beta")
    )

    prompt = f"""
    You are the Content Intelligence Engine for KeepUpdatedTrend.
    Evaluate these candidate topics and map the strongest 3 into one of our 5 content pillars:
    {json.dumps(CONTENT_PILLARS)}

    Candidates:
    {json.dumps(candidates, indent=2)}

    Score each criterion from 0 to 100:
    1. search_demand (25% weight): Evidence people are searching for this topic.
    2. trend_momentum (20% weight): Whether interest is rising or breaking now.
    3. audience_relevance (20% weight): Fit with US/UK enterprise tech & finance readers.
    4. monetization_potential (15% weight): Legitimate commercial & advertiser relevance.
    5. competition_opportunity (10% weight): Ability to offer a distinct comparison, calculation, or explainer.
    6. source_reliability (10% weight): Availability of verifiable primary sources (SEC, Fed, NIST, official docs).

    Return ONLY raw JSON with this exact structure:
    {{
      "scored_topics": [
        {{
          "headline": "Original headline",
          "primary_keyword": "Specific 3-6 word search query",
          "pillar": "Exact pillar name from list",
          "reader_question": "The exact practical question the article must answer",
          "search_demand": 85,
          "trend_momentum": 90,
          "audience_relevance": 92,
          "monetization_potential": 88,
          "competition_opportunity": 80,
          "source_reliability": 85
        }}
      ]
    }}
    """

    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.25
        )
    )

    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip(), flags=re.MULTILINE)
    scored = json.loads(cleaned).get("scored_topics", [])
    if not scored:
        return None

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    for t in scored:
        weighted = (
            t["search_demand"] * 0.25 +
            t["trend_momentum"] * 0.20 +
            t["audience_relevance"] * 0.20 +
            t["monetization_potential"] * 0.15 +
            t["competition_opportunity"] * 0.10 +
            t["source_reliability"] * 0.10
        )
        t["weighted_total"] = round(weighted, 2)
        cur.execute("""
            INSERT OR IGNORE INTO topic_queue (
                headline, primary_keyword, pillar, reader_question,
                search_demand_score, trend_momentum_score, audience_relevance_score,
                monetization_score, competition_score, source_reliability_score,
                weighted_total, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
        """, (
            t["headline"], t["primary_keyword"], t["pillar"], t["reader_question"],
            t["search_demand"], t["trend_momentum"], t["audience_relevance"],
            t["monetization_potential"], t["competition_opportunity"], t["source_reliability"],
            t["weighted_total"], now
        ))

    conn.commit()
    cur.execute("""
        SELECT id, headline, primary_keyword, pillar, reader_question, weighted_total
        FROM topic_queue
        WHERE status = 'queued'
        ORDER BY weighted_total DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "queue_id": row[0],
        "headline": row[1],
        "primary_keyword": row[2],
        "pillar": row[3],
        "reader_question": row[4],
        "weighted_total": row[5]
    }

if __name__ == "__main__":
    winner = score_and_queue_topics()
    print("Top Queued Topic:", json.dumps(winner, indent=2))
