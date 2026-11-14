import os
import re
import json
import sqlite3
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import feedparser
from datetime import datetime, timezone
from topic_engine import generate_json_with_fallback

DB_PATH = "keepupdatedtrend.db"

def fetch_authoritative_rss(keyword):
    sources = []
    queries = [
        f"{keyword} (site:sec.gov OR site:federalreserve.gov OR site:treasury.gov OR site:nist.gov)",
        f"{keyword} institutional report OR benchmark OR filing when:7d"
    ]
    for q in queries:
        encoded = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        for entry in feed.entries[:4]:
            sources.append({
                "title": entry.title.rsplit(" - ", 1)[0].strip(),
                "source": entry.get("source", {}).get("title", "Institutional Report"),
                "url": entry.link,
                "published": entry.get("published", ""),
                "type": "primary_or_news"
            })
    return sources

def fetch_arxiv_papers(keyword):
    papers = []
    try:
        clean_kw = urllib.parse.quote(re.sub(r"[^a-zA-Z0-9\s]", "", keyword))
        url = f"http://export.arxiv.org/api/query?search_query=all:{clean_kw}&start=0&max_results=2&sortBy=submittedDate&sortOrder=descending"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")[:350]
                link = entry.find("atom:id", ns).text.strip()
                papers.append({
                    "title": f"[arXiv Preprint] {title}",
                    "source": "arXiv.org (Preprint - Independently Assessed)",
                    "url": link,
                    "summary": summary,
                    "type": "preprint"
                })
    except Exception:
        pass
    return papers

def build_research_pack(topic_data):
    keyword = topic_data.get("primary_keyword") or topic_data.get("headline", "")
    raw_sources = fetch_authoritative_rss(keyword) + fetch_arxiv_papers(keyword)

    prompt = f"""
    You are the Senior Research Analyst for KeepUpdatedTrend.
    Topic Headline: "{topic_data.get('headline')}"
    Primary Keyword: "{keyword}"
    Reader Question: "{topic_data.get('reader_question', 'What is the operational and financial impact?')}"

    Collected Source Signals:
    {json.dumps(raw_sources, indent=2)}

    Compile a verified Research Pack. Separate hard facts from estimates/forecasts, and map each claim to a source from the list above (or official SEC/Fed/NIST/documentation standards).
    Return ONLY raw JSON with this exact schema:
    {{
      "core_thesis": "1-2 sentence evidence-backed answer to the reader question",
      "evaluation_criteria": ["Criterion 1", "Criterion 2", "Criterion 3"],
      "claims": [
        {{
          "claim": "Specific factual statement, metric, or mechanism",
          "source": "Official source name",
          "source_url": "URL from collected sources",
          "claim_type": "verified_fact | estimate | preprint_finding",
          "verification_status": "pending",
          "confidence": 85
        }}
      ],
      "risks_and_limitations": [
        "Concrete operational, market, or regulatory limitation 1",
        "Concrete limitation 2"
      ]
    }}
    """

    research_pack = generate_json_with_fallback(prompt, temperature=0.2)
    research_pack["raw_sources"] = raw_sources

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    for c in research_pack.get("claims", []):
        cur.execute("""
            INSERT INTO claim_records (article_id, claim, source, source_url, verification_status, confidence, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            topic_data.get("queue_id", 0),
            c.get("claim", ""),
            c.get("source", ""),
            c.get("source_url", ""),
            "pending",
            int(c.get("confidence", 0)),
            now
        ))
    conn.commit()
    conn.close()

    return research_pack
