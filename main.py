import os
import re
import json
import random
import feedparser
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# 1. Load Secrets from GitHub Environment
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_ID = os.environ["BLOG_ID"]
CLIENT_ID = os.environ["BLOGGER_CLIENT_ID"]
CLIENT_SECRET = os.environ["BLOGGER_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]

# Unified High-CPM US Tier-1 Feeds (Enterprise AI, FinTech, Markets, Cloud SaaS)
US_HIGH_CPM_FEEDS = [
    "https://news.google.com/rss/search?q=AI+Enterprise+Software+SaaS+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=S%26P+500+ETF+Institutional+Investing+Market+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Cloud+Infrastructure+Cybersecurity+FinTech+when:1d&hl=en-US&gl=US&ceid=US:en"
]

# Curated high-resolution editorial finance & tech cover images
EDITORIAL_COVERS = [
    "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1642543492481-44e81e3914a7?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1200&q=80"
]

def get_blogger_service():
    """Authenticates with Blogger API v3 headlessly using the Refresh Token."""
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
    """Fetches recent blog post titles to avoid publishing duplicates."""
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=30).execute()
        return [item["title"].lower() for item in posts.get("items", [])]
    except Exception:
        return []

def fetch_trending_topic(existing_titles):
    """Picks a fresh US trending topic with multi-source context."""
    feed_url = random.choice(US_HIGH_CPM_FEEDS)
    feed = feedparser.parse(feed_url)
    
    for entry in feed.entries[:12]:
        clean_title = entry.title.rsplit(" - ", 1)[0]
        if not any(clean_title[:25].lower() in t for t in existing_titles):
            return {
                "headline": clean_title,
                "source": entry.get("source", {}).get("title", "US Market Report"),
                "published": entry.get("published", "")
            }
    return None

def parse_json_safely(raw_text):
    """Strips markdown fences if present and parses JSON."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)

def generate_structured_article(topic_data):
    """Generates structured JSON data so Python can assemble a uniform, animated layout."""
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
    You are a Senior US Institutional Finance & Enterprise Tech Editor.
    Based on this trending catalyst: "{topic_data['headline']}"

    Produce a strictly disciplined, analytical guide (~1,000 words) for a US/UK executive and investor audience.
    Return ONLY a raw JSON object with this exact schema:
    {{
      "seo_title": "Clear, authoritative title under 64 characters",
      "category_badge": "One of: ENTERPRISE AI | MARKET STRATEGY | CLOUD & SAAS | FINTECH ANALYSIS",
      "labels": ["Tag1", "Tag2", "Tag3"],
      "executive_takeaways": [
        "Takeaway 1 (1 concise sentence with a concrete metric or mechanism)",
        "Takeaway 2 (1 concise sentence)",
        "Takeaway 3 (1 concise sentence)"
      ],
      "intro_paragraph": "Strong 2-paragraph opening establishing the market catalyst and why it matters now (plain text, separated by \\n\\n).",
      "sections": [
        {{
          "heading": "1. Core Catalyst & Market Mechanics",
          "body_html": "<p>Detailed analysis...</p><p>Second paragraph...</p>"
        }},
        {{
          "heading": "2. Financial & Operational Implications",
          "body_html": "<p>Detailed analysis...</p><ul><li><strong>Key Factor:</strong> Explanation...</li><li><strong>Risk Vector:</strong> Explanation...</li></ul>"
        }},
        {{
          "heading": "3. Strategic Implementation Framework",
          "body_html": "<p>Step-by-step actionable blueprint for decision-makers...</p>"
        }}
      ],
      "table": {{
        "caption": "Comparative Benchmark & Metric Breakdown",
        "headers": ["Metric / Option", "Baseline / Legacy", "Modern / Optimized", "Primary Impact"],
        "rows": [
          ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3", "Row 1 Col 4"],
          ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3", "Row 2 Col 4"],
          ["Row 3 Col 1", "Row 3 Col 2", "Row 3 Col 3", "Row 3 Col 4"],
          ["Row 4 Col 1", "Row 4 Col 2", "Row 4 Col 3", "Row 4 Col 4"]
        ]
      }},
      "faqs": [
        {{"q": "Specific high-intent question 1?", "a": "Direct, authoritative 2-3 sentence answer."}},
        {{"q": "Specific high-intent question 2?", "a": "Direct, authoritative 2-3 sentence answer."}},
        {{"q": "Specific high-intent question 3?", "a": "Direct, authoritative 2-3 sentence answer."}},
        {{"q": "Specific high-intent question 4?", "a": "Direct, authoritative 2-3 sentence answer."}}
      ]
    }}
    """

    last_error = None
    for model_name in available_models:
        try:
            print(f"Generating structured article with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.6
                )
            )
            return parse_json_safely(response.text)
        except Exception as e:
            print(f"Skipped {model_name}: {e}")
            last_error = e

    raise last_error

def render_animated_responsive_html(data):
    """Wraps the structured JSON into an animated, mobile-first and desktop-optimized theme."""
    img_url = random.choice(EDITORIAL_COVERS)
    safe_alt = data["seo_title"].replace('"', '&quot;')
    badge = data.get("category_badge", "MARKET ANALYSIS")

    # 1. Embedded CSS3 Keyframe Animations & Mobile/PC Responsive Rules
    css_animations = """
    <style>
      @keyframes ktFadeUp {
        0% { opacity: 0; transform: translateY(18px); }
        100% { opacity: 1; transform: translateY(0); }
      }
      @keyframes ktPulseDot {
        0%, 100% { transform: scale(1); opacity: 1; box-shadow: 0 0 0 0 rgba(0, 229, 255, 0.7); }
        50% { transform: scale(1.15); opacity: 0.85; box-shadow: 0 0 0 6px rgba(0, 229, 255, 0); }
      }
      @keyframes ktShimmerBorder {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
      }
      .kt-wrap {
        max-width: 840px;
        margin: 0 auto;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        color: #1e293b;
        line-height: 1.75;
        font-size: 16px;
        box-sizing: border-box;
        padding: 4px;
      }
      .kt-anim-1 { animation: ktFadeUp 0.55s ease-out 0.05s both; }
      .kt-anim-2 { animation: ktFadeUp 0.65s ease-out 0.15s both; }
      .kt-anim-3 { animation: ktFadeUp 0.75s ease-out 0.25s both; }
      .kt-anim-4 { animation: ktFadeUp 0.85s ease-out 0.35s both; }
      .kt-cover-box {
        overflow: hidden;
        border-radius: 14px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.18);
        margin-bottom: 26px;
      }
      .kt-cover-box img {
        width: 100%;
        max-width: 840px;
        height: auto;
        max-height: 430px;
        object-fit: cover;
        display: block;
        transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
      }
      .kt-cover-box:hover img {
        transform: scale(1.03);
      }
      .kt-exec-card {
        background: linear-gradient(135deg, #000814 0%, #001229 100%);
        color: #f8fafc;
        border-left: 4px solid #00e5ff;
        border-radius: 12px;
        padding: 20px 22px;
        margin-bottom: 28px;
        box-shadow: 0 8px 20px rgba(0, 8, 20, 0.16);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
      }
      .kt-exec-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 28px rgba(0, 229, 255, 0.15);
      }
      .kt-section-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 22px 24px;
        margin-bottom: 24px;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
        transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
      }
      .kt-section-card:hover {
        transform: translateY(-2px);
        border-color: #38bdf8;
        box-shadow: 0 8px 22px rgba(41, 98, 255, 0.08);
      }
      .kt-table-row {
        transition: background-color 0.2s ease;
      }
      .kt-table-row:hover {
        background-color: #e0f2fe !important;
      }
      .kt-faq-item {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        margin-bottom: 12px;
        overflow: hidden;
        transition: border-color 0.25s ease, box-shadow 0.25s ease;
      }
      .kt-faq-item:hover {
        border-color: #2962ff;
        box-shadow: 0 4px 12px rgba(41, 98, 255, 0.08);
      }
      .kt-faq-item summary {
        padding: 15px 18px;
        font-size: 16px;
        font-weight: 700;
        color: #0f172a;
        cursor: pointer;
        list-style: none;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .kt-faq-item summary::-webkit-details-marker {
        display: none;
      }
      .kt-faq-icon {
        color: #2962ff;
        font-weight: 800;
        font-size: 18px;
        transition: transform 0.3s ease;
      }
      .kt-faq-item[open] .kt-faq-icon {
        transform: rotate(45deg);
      }
      .kt-faq-answer {
        padding: 0 18px 16px 18px;
        color: #334155;
        font-size: 15px;
        border-top: 1px solid #e2e8f0;
        padding-top: 12px;
        animation: ktFadeUp 0.3s ease-out both;
      }
      @media (max-width: 640px) {
        .kt-wrap { font-size: 15.5px; }
        .kt-section-card { padding: 16px 16px; }
        .kt-exec-card { padding: 16px 16px; }
      }
    </style>
    """

    html = [css_animations, '<div class="kt-wrap">']

    # 2. Animated Live Category Badge
    html.append(
        f'<div class="kt-anim-1" style="margin-bottom: 14px; display: flex; align-items: center; gap: 10px;">'
        f'<span style="display: inline-flex; align-items: center; gap: 8px; background: #000814; color: #00e5ff; font-size: 12px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; padding: 6px 14px; border-radius: 999px; border: 1px solid rgba(0,229,255,0.3);">'
        f'<span style="width: 8px; height: 8px; background: #10b981; border-radius: 50%; display: inline-block; animation: ktPulseDot 2s infinite;"></span>'
        f'{badge}'
        f'</span>'
        f'</div>'
    )

    # 3. Featured Cover Image with Smooth Zoom Hover (Blogger picks this <img> as thumbnail)
    html.append(
        f'<div class="separator kt-cover-box kt-anim-1" style="clear: both; text-align: center;">'
        f'<a href="{img_url}" imageanchor="1" style="display: block; margin: 0;">'
        f'<img border="0" src="{img_url}" alt="{safe_alt}" title="{safe_alt}" />'
        f'</a></div>'
    )

    # 4. Deepsea Cyber-Slate Executive Summary Card
    takeaways_li = "".join(
        f'<li style="margin-bottom: 10px; color: #e2e8f0;">{t}</li>'
        for t in data.get("executive_takeaways", [])
    )
    html.append(
        f'<div class="kt-exec-card kt-anim-2">'
        f'<div style="font-size: 12.5px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.2px; color: #00e5ff; margin-bottom: 10px;">⚡ Executive Intelligence Summary</div>'
        f'<ul style="margin: 0; padding-left: 20px; font-size: 15px; line-height: 1.65;">{takeaways_li}</ul>'
        f'</div>'
    )

    # 5. Intro Paragraphs
    html.append('<div class="kt-anim-3">')
    for para in data.get("intro_paragraph", "").split("\n\n"):
        if para.strip():
            html.append(f'<p style="margin-bottom: 18px; font-size: 16.5px; color: #334155;">{para.strip()}</p>')
    html.append('</div>')

    # 6. Disciplined Content Section Cards + Interactive Comparison Table
    sections = data.get("sections", [])
    for idx, sec in enumerate(sections):
        html.append(
            f'<div class="kt-section-card kt-anim-4">'
            f'<h2 style="font-size: 21px; font-weight: 800; color: #0f172a; margin-top: 0; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 2px solid #e2e8f0;">{sec.get("heading", "")}</h2>'
            f'<div style="color: #334155;">{sec.get("body_html", "")}</div>'
            f'</div>'
        )
        # Insert the mobile-scrollable comparison table right after Section 2
        if idx == 1 and "table" in data:
            tbl = data["table"]
            headers_html = "".join(
                f'<th style="padding: 13px 15px; text-align: left; background: #000814; color: #00e5ff; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; white-space: nowrap;">{h}</th>'
                for h in tbl.get("headers", [])
            )
            rows_html = ""
            for r_idx, row in enumerate(tbl.get("rows", [])):
                bg = "#ffffff" if r_idx % 2 == 0 else "#f8fafc"
                cells = "".join(
                    f'<td style="padding: 12px 15px; border-bottom: 1px solid #e2e8f0; font-size: 14px; color: #1e293b; min-width: 125px;">{c}</td>'
                    for c in row
                )
                rows_html += f'<tr class="kt-table-row" style="background: {bg};">{cells}</tr>'

            html.append(
                f'<div class="kt-anim-4" style="margin: 30px 0;">'
                f'<div style="font-size: 13.5px; font-weight: 800; color: #0f172a; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.6px;">📊 {tbl.get("caption", "Comparative Analysis")}</div>'
                f'<div style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid #cbd5e1; border-radius: 12px; box-shadow: 0 4px 14px rgba(0,8,20,0.06);">'
                f'<table style="width: 100%; border-collapse: collapse; min-width: 520px;">'
                f'<thead><tr>{headers_html}</tr></thead>'
                f'<tbody>{rows_html}</tbody>'
                f'</table></div>'
                f'<div style="font-size: 12px; color: #64748b; margin-top: 6px; text-align: right;"><em>*Swipe horizontally on mobile to inspect all columns</em></div>'
                f'</div>'
            )

    # 7. Interactive Animated Accordion FAQs (Zero JS required)
    if data.get("faqs"):
        html.append(
            '<div class="kt-anim-4" style="margin-top: 36px;">'
            '<h2 style="font-size: 21px; font-weight: 800; color: #0f172a; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0;">Frequently Asked Questions</h2>'
        )
        for faq in data["faqs"]:
            html.append(
                f'<details class="kt-faq-item">'
                f'<summary><span>{faq.get("q", "")}</span><span class="kt-faq-icon">+</span></summary>'
                f'<div class="kt-faq-answer">{faq.get("a", "")}</div>'
                f'</details>'
            )
        html.append('</div>')

    html.append('</div>')
    return "\n".join(html)

def main():
    service = get_blogger_service()
    existing_titles = get_existing_titles(service)
    
    topic = fetch_trending_topic(existing_titles)
    if not topic:
        print("No new unique trending topics found in this cycle.")
        return

    print(f"Generating animated structured article for trend: {topic['headline']}")
    article_data = generate_structured_article(topic)
    formatted_html = render_animated_responsive_html(article_data)

    body = {
        "kind": "blogger#post",
        "blog": {"id": BLOG_ID},
        "title": article_data["seo_title"],
        "content": formatted_html,
        "labels": article_data.get("labels", ["Market Analysis"])[:5]
    }

    post = service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
    print(f"Successfully published animated article! Live URL: {post.get('url')}")

if __name__ == "__main__":
    main()
