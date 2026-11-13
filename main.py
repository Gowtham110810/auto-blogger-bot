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

# High-CPM US Tier-1 Google News RSS Feeds (Finance, AI, Cloud/SaaS, Investing)
US_HIGH_CPM_FEEDS = [
    "https://news.google.com/rss/search?q=AI+Enterprise+Software+SaaS+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Personal+Finance+ETF+Investing+Market+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Cloud+Computing+Cybersecurity+Tech+when:1d&hl=en-US&gl=US&ceid=US:en"
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
        posts = service.posts().list(blogId=BLOG_ID, maxResults=25).execute()
        return [item["title"].lower() for item in posts.get("items", [])]
    except Exception:
        return []

def fetch_trending_topic(existing_titles):
    """Picks a fresh US trending topic with multi-source context."""
    feed_url = random.choice(US_HIGH_CPM_FEEDS)
    feed = feedparser.parse(feed_url)
    
    for entry in feed.entries[:10]:
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

def generate_high_cpm_article(topic_data):
    """Automatically discovers available Gemini models on your API key and generates the post."""
    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(api_version="v1beta")
    )

    # Dynamically query the API for all Gemini text-generation models enabled for this key
    available_models = []
    for m in client.models.list():
        name = m.name.replace("models/", "")
        actions = getattr(m, "supported_actions", []) or []
        if "gemini" in name and "embedding" not in name and "imagen" not in name and "veo" not in name:
            if not actions or "generateContent" in actions:
                available_models.append(name)

    # Prioritize fast Flash/Pro models first
    available_models.sort(key=lambda x: (0 if "flash" in x else 1, x), reverse=True)
    print(f"Detected available models for your key: {available_models[:6]}")

    prompt = f"""
    You are an expert US Financial and Enterprise Tech Analyst.
    Based on this trending catalyst: "{topic_data['headline']}"
    
    Write an original, comprehensive, 1,000-word analytical guide tailored for a US/UK audience.
    Do NOT just summarize the news—provide deep actionable frameworks, financial/technical implications, and comparisons.

    Return ONLY a raw JSON object (no markdown formatting or backticks) with these exact keys:
    {{
      "seo_title": "Click-worthy, SEO-optimized title (under 65 chars, different from original headline)",
      "labels": ["Tag1", "Tag2", "Tag3"],
      "html_content": "Full HTML body using ONLY <h2>, <h3>, <p>, <ul>, <li>, <strong>, and a styled <table> comparing key metrics/options, followed by a 4-question FAQ section."
    }}
    """

    last_error = None
    for model_name in available_models:
        try:
            print(f"Generating article with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7
                )
            )
            return parse_json_safely(response.text)
        except Exception as e:
            print(f"Skipped {model_name}: {e}")
            last_error = e

    raise last_error

def main():
    service = get_blogger_service()
    existing_titles = get_existing_titles(service)
    
    topic = fetch_trending_topic(existing_titles)
    if not topic:
        print("No new unique trending topics found in this cycle.")
        return

    print(f"Generating article for trend: {topic['headline']}")
    article = generate_high_cpm_article(topic)

    body = {
        "kind": "blogger#post",
        "blog": {"id": BLOG_ID},
        "title": article["seo_title"],
        "content": article["html_content"],
        "labels": article["labels"][:5]
    }

    post = service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
    print(f"Successfully published! Live URL: {post.get('url')}")

if __name__ == "__main__":
    main()
