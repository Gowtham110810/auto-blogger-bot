import os
import re
import json
import random
import sqlite3
import requests
from datetime import datetime, timezone
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Import your 3 P1 Roadmap Modules
import topic_engine
import research_engine
import fact_checker

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_ID = os.environ["BLOG_ID"]
CLIENT_ID = os.environ["BLOGGER_CLIENT_ID"]
CLIENT_SECRET = os.environ["BLOGGER_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
DEVTO_API_KEY = os.environ.get("DEVTO_API_KEY", "").strip()

DB_PATH = "keepupdatedtrend.db"

EDITORIAL_COVERS = [
    "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1639762681485-074b7f938ba0?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1642543492481-44e81e3914a7?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1200&q=80"
]

def ensure_valid_sqlite_db():
    """Replaces manually created text placeholders with a valid binary SQLite database."""
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "rb") as f:
                header = f.read(16)
            if header and not header.startswith(b"SQLite format 3"):
                os.remove(DB_PATH)
        except Exception:
            pass
    topic_engine.init_db()

def log_stage(stage, status, details=""):
    """Records pipeline execution milestones in SQLite run_history."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_history (stage, status, details, logged_at) VALUES (?, ?, ?, ?)",
            (stage, status, details[:500], datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_blogger_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"]
    )
    return build("blogger", "v3", credentials=creds)

def get_existing_titles(service):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=30).execute()
        return [item["title"].lower() for item in posts.get("items", [])]
    except Exception:
        return []

def get_Internal_links():
    """Fetches up to 2 related past articles from SQLite for on-page internal linking."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT title, url FROM articles_catalogue WHERE publish_state = 'LIVE' ORDER BY id DESC LIMIT 3")
        rows = cur.fetchall()
        conn.close()
        return [{"title": r[0], "url": r[1]} for r in rows if r[0] and r[1]]
    except Exception:
        return []

def parse_json_safely(raw_text):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)

def generate_research_grounded_article(topic_data, research_pack):
    """Drafts an analytical article grounded in the collected Research Pack."""
    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(api_version="v1beta")
    )

    available_models = []
    for m in client.models.list():
        name = m.name.replace("models/", "")
        actions = getattr(m, "supported_actions", []) or []
        if "gemini" in name and "embedding" not in name and "imagen" not in name and "veo" not in name:
            if not actions or "generateContent" in actions:
                available_models.append(name)
    available_models.sort(key=lambda x: (0 if "flash" in x else 1, x), reverse=True)

    prompt = f"""
    You are a Senior US Institutional Finance & Enterprise Tech Editor for KeepUpdatedTrend.
    Draft a comprehensive, research-grounded analytical guide (~1,000 words) based on:
    - Target Headline: "{topic_data.get('headline')}"
    - Primary Search Keyword: "{topic_data.get('primary_keyword')}"
    - Content Pillar: "{topic_data.get('pillar')}"
    - Core Reader Question: "{topic_data.get('reader_question')}"

    Verified Research Pack & Claims:
    {json.dumps(research_pack, indent=2)}

    Requirements:
    - Include original comparisons, transparent evaluation criteria, and explicit risk/limitation analysis.
    - Clearly distinguish between verified facts, illustrative calculations, and forecasts.
    - Return ONLY raw JSON matching this exact schema:
    {{
      "seo_title": "High-CTR, search-intent title under 64 characters incorporating the primary keyword",
      "meta_description": "Clear 150-character summary answering the reader question without keyword stuffing",
      "category_badge": "One of: ENTERPRISE AI | WALL STREET STRATEGY | CLOUD & SAAS | FINTECH INTEL",
      "read_time": "5 MIN READ",
      "impact_score": "VERIFIED RESEARCH",
      "labels": ["{topic_data.get('pillar', 'Market Analysis')}", "US Markets", "Enterprise Tech"],
      "executive_takeaways": [
        "Takeaway 1 grounded in research pack",
        "Takeaway 2 grounded in research pack",
        "Takeaway 3 grounded in research pack"
      ],
      "visual_metrics": [
        {{"label": "Metric 1 Name", "percent": 82, "display_value": "82% Benchmark"}},
        {{"label": "Metric 2 Name", "percent": 68, "display_value": "+68% Efficiency"}},
        {{"label": "Risk / Volatility Exposure", "percent": 40, "display_value": "40% Moderate"}}
      ],
      "intro_paragraph": "Strong 2-paragraph opening answering the reader question directly (separated by \\n\\n).",
      "sections": [
        {{
          "heading": "1. Core Catalyst & Architecture Breakdown",
          "body_html": "<p>Detailed evidence-backed analysis...</p><p>Second paragraph...</p>"
        }},
        {{
          "heading": "2. Quantitative Comparison & Operational Impact",
          "body_html": "<p>Detailed analysis...</p><ul><li><strong>Primary Driver:</strong> Explanation...</li><li><strong>Key Limitation / Risk:</strong> Explanation...</li></ul>"
        }},
        {{
          "heading": "3. Decision-Maker Execution Blueprint",
          "body_html": "<p>Practical step-by-step implementation framework...</p>"
        }}
      ],
      "table": {{
        "caption": "Comparative Evaluation Matrix",
        "headers": ["Evaluation Criterion", "Legacy Baseline", "Modern Architecture", "Net Operational Impact"],
        "rows": [
          ["Criterion 1", "Baseline 1", "Modern 1", "Impact 1"],
          ["Criterion 2", "Baseline 2", "Modern 2", "Impact 2"],
          ["Criterion 3", "Baseline 3", "Modern 3", "Impact 3"],
          ["Risk Profile", "High Overhead", "Managed Controls", "Audited Compliance"]
        ]
      }},
      "faqs": [
        {{"q": "High-intent reader question 1?", "a": "Direct, authoritative 2-3 sentence answer."}},
        {{"q": "High-intent reader question 2?", "a": "Direct, authoritative 2-3 sentence answer."}},
        {{"q": "High-intent reader question 3?", "a": "Direct, authoritative 2-3 sentence answer."}}
      ]
    }}
    """

    last_error = None
    for model_name in available_models:
        try:
            print(f"Drafting research-backed article with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.45
                )
            )
            return parse_json_safely(response.text)
        except Exception as e:
            print(f"Skipped {model_name}: {e}")
            last_error = e
    raise last_error

def render_deepsea_interactive_html(data, img_url, references_html="", internal_links=None):
    """Renders the Deepsea dark-glassmorphic layout with JSON-LD Schema, Internal Links, and Reference Ledger."""
    safe_alt = data["seo_title"].replace('"', '&quot;')
    badge = data.get("category_badge", "MARKET ANALYSIS")
    read_time = data.get("read_time", "5 MIN READ")
    impact_score = data.get("impact_score", "VERIFIED RESEARCH")

    # JSON-LD Article Schema for Google Search
    schema_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": data["seo_title"],
        "description": data.get("meta_description", ""),
        "image": [img_url],
        "author": {"@type": "Organization", "name": "KeepUpdatedTrend Research"},
        "publisher": {"@type": "Organization", "name": "KeepUpdatedTrend"}
    }

    css_styles = """
    <style>
      @keyframes dsFadeUp {
        0% { opacity: 0; transform: translateY(20px); }
        100% { opacity: 1; transform: translateY(0); }
      }
      @keyframes dsGrowBar {
        0% { width: 0%; }
      }
      @keyframes dsPulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        50% { box-shadow: 0 0 0 7px rgba(16, 185, 129, 0); }
      }
      .ds-shell {
        max-width: 840px;
        margin: 0 auto;
        background: #000814;
        color: #e2e8f0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        line-height: 1.78;
        font-size: 16px;
        padding: 20px;
        border-radius: 18px;
        border: 1px solid rgba(0, 229, 255, 0.2);
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
        box-sizing: border-box;
      }
      .ds-card {
        background: #001229;
        border: 1px solid rgba(41, 98, 255, 0.32);
        border-radius: 14px;
        padding: 22px 24px;
        margin-bottom: 24px;
        animation: dsFadeUp 0.65s ease-out both;
        transition: transform 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
      }
      .ds-card:hover {
        transform: translateY(-3px);
        border-color: #00e5ff;
        box-shadow: 0 10px 28px rgba(0, 229, 255, 0.14);
      }
      .ds-card p, .ds-card li { color: #cbd5e1 !important; }
      .ds-card strong { color: #00e5ff !important; }
      .ds-cover {
        overflow: hidden;
        border-radius: 14px;
        margin-bottom: 24px;
        border: 1px solid rgba(0, 229, 255, 0.25);
        position: relative;
      }
      .ds-cover img {
        width: 100%;
        max-height: 420px;
        object-fit: cover;
        display: block;
        transition: transform 0.55s ease;
      }
      .ds-cover:hover img { transform: scale(1.04); }
      .ds-faq {
        background: #001229;
        border: 1px solid rgba(41, 98, 255, 0.35);
        border-radius: 12px;
        margin-bottom: 12px;
        overflow: hidden;
      }
      .ds-faq summary {
        padding: 16px 20px;
        font-weight: 700;
        color: #ffffff;
        cursor: pointer;
        list-style: none;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .ds-faq summary::-webkit-details-marker { display: none; }
      @media (max-width: 640px) {
        .ds-shell { padding: 14px; font-size: 15.5px; }
        .ds-card { padding: 16px; }
      }
    </style>
    """

    html = [
        f'<script type="application/ld+json">{json.dumps(schema_ld)}</script>',
        css_styles,
        '<div class="ds-shell">'
    ]

    # 1. Top Status Bar
    html.append(
        f'<div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 16px;">'
        f'<span style="display: inline-flex; align-items: center; gap: 8px; background: rgba(0, 229, 255, 0.12); color: #00e5ff; font-size: 12px; font-weight: 800; letter-spacing: 1px; padding: 6px 14px; border-radius: 999px; border: 1px solid rgba(0, 229, 255, 0.4);">'
        f'<span style="width: 8px; height: 8px; background: #10b981; border-radius: 50%; display: inline-block; animation: dsPulse 2s infinite;"></span>'
        f'{badge}</span>'
        f'<div style="display: flex; gap: 8px; font-size: 11.5px; font-weight: 700;">'
        f'<span style="background: #001229; color: #94a3b8; padding: 5px 11px; border-radius: 6px; border: 1px solid #1e293b;">⏱ {read_time}</span>'
        f'<span style="background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 5px 11px; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.35);">✓ {impact_score}</span>'
        f'</div></div>'
    )

    # 2. Featured Cover Image
    html.append(
        f'<div class="separator ds-cover" style="clear: both; text-align: center;">'
        f'<a href="{img_url}" imageanchor="1" style="display: block; margin: 0;">'
        f'<img border="0" src="{img_url}" alt="{safe_alt}" title="{safe_alt}" />'
        f'</a></div>'
    )

    # 3. Executive Takeaways Box
    takeaways_li = "".join(
        f'<li style="margin-bottom: 10px; color: #f1f5f9;">{t}</li>'
        for t in data.get("executive_takeaways", [])
    )
    html.append(
        f'<div class="ds-card" style="border-left: 4px solid #00e5ff; background: linear-gradient(135deg, #001229 0%, #001d3d 100%);">'
        f'<div style="font-size: 12.5px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.2px; color: #00e5ff; margin-bottom: 10px;">⚡ Executive Terminal Brief</div>'
        f'<ul style="margin: 0; padding-left: 20px; font-size: 15px;">{takeaways_li}</ul>'
        f'</div>'
    )

    # 4. Intro Paragraphs
    html.append('<div class="ds-card">')
    for para in data.get("intro_paragraph", "").split("\n\n"):
        if para.strip():
            html.append(f'<p style="margin-bottom: 16px; font-size: 16.5px; color: #e2e8f0;">{para.strip()}</p>')
    html.append('</div>')

    # 5. Visual Analytics Bars
    if data.get("visual_metrics"):
        bars_html = ""
        bar_colors = [
            "linear-gradient(90deg, #2962ff, #00e5ff)",
            "linear-gradient(90deg, #00e5ff, #10b981)",
            "linear-gradient(90deg, #6366f1, #38bdf8)"
        ]
        for idx, m in enumerate(data["visual_metrics"]):
            pct = max(15, min(98, int(m.get("percent", 75))))
            grad = bar_colors[idx % len(bar_colors)]
            bars_html += (
                f'<div style="margin-bottom: 16px;">'
                f'<div style="display: flex; justify-content: space-between; font-size: 13.5px; font-weight: 700; margin-bottom: 6px;">'
                f'<span style="color: #f8fafc;">{m.get("label", "Metric")}</span>'
                f'<span style="color: #00e5ff;">{m.get("display_value", f"{pct}%")}</span>'
                f'</div>'
                f'<div style="width: 100%; height: 10px; background: #000814; border-radius: 999px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08);">'
                f'<div style="width: {pct}%; height: 100%; background: {grad}; border-radius: 999px; animation: dsGrowBar 1.4s ease-out both;"></div>'
                f'</div></div>'
            )
        html.append(
            f'<div class="ds-card">'
            f'<div style="font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #10b981; margin-bottom: 16px;">📈 Quantitative Market Telemetry</div>'
            f'{bars_html}</div>'
        )

    # 6. Analytical Sections + Swipeable Comparison Table
    sections = data.get("sections", [])
    for idx, sec in enumerate(sections):
        html.append(
            f'<div class="ds-card">'
            f'<h2 style="font-size: 20.5px; font-weight: 800; color: #ffffff; margin-top: 0; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid rgba(0, 229, 255, 0.25);">{sec.get("heading", "")}</h2>'
            f'<div>{sec.get("body_html", "")}</div>'
            f'</div>'
        )
        if idx == 1 and "table" in data:
            tbl = data["table"]
            headers_html = "".join(
                f'<th style="padding: 13px 15px; text-align: left; background: #001d3d; color: #00e5ff; font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; white-space: nowrap; border-bottom: 2px solid #2962ff;">{h}</th>'
                for h in tbl.get("headers", [])
            )
            rows_html = ""
            for r_idx, row in enumerate(tbl.get("rows", [])):
                bg = "#001229" if r_idx % 2 == 0 else "#001833"
                cells = "".join(
                    f'<td style="padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.07); font-size: 14px; color: #e2e8f0; min-width: 125px;">{c}</td>'
                    for c in row
                )
                rows_html += f'<tr style="background: {bg};">{cells}</tr>'

            html.append(
                f'<div style="margin: 28px 0;">'
                f'<div style="font-size: 13px; font-weight: 800; color: #00e5ff; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.8px;">📊 {tbl.get("caption", "Comparative Benchmark")}</div>'
                f'<div style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 12px;">'
                f'<table style="width: 100%; border-collapse: collapse; min-width: 520px;">'
                f'<thead><tr>{headers_html}</tr></thead>'
                f'<tbody>{rows_html}</tbody>'
                f'</table></div>'
                f'<div style="font-size: 12px; color: #64748b; margin-top: 6px; text-align: right;"><em>*Swipe horizontally on mobile to inspect full matrix</em></div>'
                f'</div>'
            )

    # 7. Internal Links Card (If previous posts exist in SQLite)
    if internal_links:
        links_li = "".join(
            f'<li style="margin-bottom: 8px;"><a href="{ item["url"] }" style="color: #00e5ff; font-weight: 600; text-decoration: underline;">{ item["title"] }</a></li>'
            for item in internal_links
        )
        html.append(
            f'<div class="ds-card" style="border-left: 3px solid #2962ff;">'
            f'<div style="font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #00e5ff; margin-bottom: 10px;">🔗 Related KeepUpdatedTrend Briefings</div>'
            f'<ul style="margin: 0; padding-left: 18px;">{links_li}</ul>'
            f'</div>'
        )

    # 8. Authoritative References & Fact-Checking Ledger
    if references_html:
        html.append(references_html)

    # 9. Interactive FAQ Accordions
    if data.get("faqs"):
        html.append(
            '<div style="margin-top: 32px;">'
            '<h2 style="font-size: 20.5px; font-weight: 800; color: #ffffff; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid rgba(0, 229, 255, 0.25);">Frequently Asked Questions</h2>'
        )
        for faq in data["faqs"]:
            html.append(
                f'<details class="ds-faq">'
                f'<summary><span>{faq.get("q", "")}</span><span style="color: #00e5ff; font-weight: 800; font-size: 18px;">+</span></summary>'
                f'<div style="padding: 14px 20px; color: #cbd5e1; font-size: 15px; border-top: 1px solid rgba(255,255,255,0.08);">{faq.get("a", "")}</div>'
                f'</details>'
            )
        html.append('</div>')

    # 10. Bottom Engagement Banner
    html.append(
        '<div style="margin-top: 30px; background: linear-gradient(135deg, #2962ff 0%, #001229 100%); border: 1px solid #00e5ff; border-radius: 14px; padding: 20px; text-align: center;">'
        '<div style="font-size: 16px; font-weight: 800; color: #ffffff; margin-bottom: 6px;">Stay Ahead of Institutional Market Shifts</div>'
        '<div style="font-size: 13.5px; color: #cbd5e1;">Bookmark this terminal for research-verified US Enterprise AI, SaaS &amp; ETF breakdowns.</div>'
        '</div></div>'
    )
    return "\n".join(html)

def syndicate_to_devto(article_data, live_blog_url, cover_url):
    if not DEVTO_API_KEY:
        return
    takeaways_md = "\n".join(f"- {t}" for t in article_data.get("executive_takeaways", []))
    sections_md = ""
    for sec in article_data.get("sections", [])[:2]:
        clean_text = re.sub(r"<[^>]+>", "", sec.get("body_html", ""))
        sections_md += f"\n\n## {sec.get('heading', '')}\n{clean_text}"

    markdown_body = (
        f"![Cover]({cover_url})\n\n"
        f"### Executive Intelligence Summary\n{takeaways_md}\n\n"
        f"{article_data.get('intro_paragraph', '')}"
        f"{sections_md}\n\n"
        f"---\n"
        f"### 📊 View the Full Interactive Benchmark Matrix & Verification Ledger\n"
        f"👉 **[Read the Full Analysis on KeepUpdatedTrend]({live_blog_url})**"
    )

    clean_tags = [re.sub(r"[^a-z0-9]", "", t.lower())[:20] for t in article_data.get("labels", [])]
    clean_tags = [t for t in clean_tags if t][:4] or ["ai", "finance", "cloud", "tech"]

    payload = {
        "article": {
            "title": article_data["seo_title"],
            "published": True,
            "body_markdown": markdown_body,
            "tags": clean_tags,
            "canonical_url": live_blog_url
        }
    }
    try:
        resp = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=20
        )
        print(f"Dev.to status: {resp.status_code}")
    except Exception as e:
        print(f"Dev.to syndication skipped: {e}")

def main():
    ensure_valid_sqlite_db()
    service = get_blogger_service()
    existing_titles = get_existing_titles(service)

    # Stage 1: Topic Discovery & Scoring (topic_engine.py)
    print("Stage 1: Scoring candidate topics via topic_engine.py...")
    topic = topic_engine.score_and_queue_topics(existing_titles)
    if not topic:
        log_stage("discover", "skipped", "No unique topics found")
        print("No new unique trending topics found in this cycle.")
        return
    log_stage("discover", "passed", f"Selected: {topic['primary_keyword']} ({topic['weighted_total']})")

    # Stage 2: Authoritative Research Collection (research_engine.py)
    print(f"Stage 2: Building research pack for '{topic['primary_keyword']}'...")
    research_pack = research_engine.build_research_pack(topic)
    log_stage("research", "passed", f"Extracted {len(research_pack.get('claims', []))} claims")

    # Stage 3: Research-Grounded Drafting
    print("Stage 3: Drafting article grounded in research pack...")
    draft_data = generate_research_grounded_article(topic, research_pack)

    # Stage 4: Fact-Checking & Verification Gate (fact_checker.py)
    print("Stage 4: Running fact_checker.py verification gate...")
    verified_data = fact_checker.verify_and_refine_article(
        draft_data, research_pack, queue_id=topic.get("queue_id", 0)
    )
    references_html = fact_checker.render_references_html(verified_data)
    internal_links = get_Internal_links()

    # Stage 5: Render & Publish
    cover_url = random.choice(EDITORIAL_COVERS)
    formatted_html = render_deepsea_interactive_html(
        verified_data, cover_url, references_html=references_html, internal_links=internal_links
    )

    is_draft = not verified_data.get("gate_passed", True)
    body = {
        "kind": "blogger#post",
        "blog": {"id": BLOG_ID},
        "title": verified_data["seo_title"],
        "content": formatted_html,
        "labels": verified_data.get("labels", ["Market Analysis"])[:5]
    }

    post = service.posts().insert(blogId=BLOG_ID, body=body, isDraft=is_draft).execute()
    live_url = post.get("url", "")
    state_label = "DRAFT_REVIEW" if is_draft else "LIVE"
    print(f"Successfully published ({state_label})! URL: {live_url}")

    # Record in SQLite Catalogue & Mark Topic Completed
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE topic_queue SET status = 'published' WHERE id = ?",
        (topic.get("queue_id", 0),)
    )
    cur.execute("""
        INSERT OR IGNORE INTO articles_catalogue (title, url, slug, pillar, primary_keyword, publish_state, published_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        verified_data["seo_title"],
        live_url,
        re.sub(r"[^a-z0-9]+", "-", verified_data["seo_title"].lower()).strip("-"),
        topic.get("pillar", "Enterprise AI"),
        topic.get("primary_keyword", ""),
        state_label,
        datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    conn.close()
    log_stage("publish", state_label, live_url)

    if not is_draft and live_url:
        syndicate_to_devto(verified_data, live_url, cover_url)

if __name__ == "__main__":
    main()
