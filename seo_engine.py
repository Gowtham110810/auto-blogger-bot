import re
import json
import sqlite3

DB_PATH = "keepupdatedtrend.db"
SITE_URL = "https://keepupdatedtrend.blogspot.com"

def generate_clean_slug(title, primary_keyword=""):
    """Generates a short, readable, descriptive URL slug."""
    base = primary_keyword if primary_keyword else title
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    words = slug.split("-")[:7]
    return "-".join(words)

def find_relevant_internal_links(pillar, primary_keyword, limit=3):
    """Searches the SQLite catalogue for published articles matching the same pillar or topic keywords."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT title, url, pillar, primary_keyword
            FROM articles_catalogue
            WHERE publish_state = 'LIVE' AND url IS NOT NULL AND url != ''
            ORDER BY id DESC
            LIMIT 40
        """)
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return []

    kw_tokens = set(re.findall(r"[a-z0-9]+", (primary_keyword or "").lower()))
    scored_links = []

    for title, url, art_pillar, art_kw in rows:
        score = 0
        if art_pillar and pillar and art_pillar.lower() == pillar.lower():
            score += 3
        art_tokens = set(re.findall(r"[a-z0-9]+", f"{title} {art_kw}".lower()))
        overlap = len(kw_tokens.intersection(art_tokens))
        score += overlap * 2
        scored_links.append((score, {"title": title, "url": url, "pillar": art_pillar or "Briefing"}))

    scored_links.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_links[:limit]]

def build_and_validate_schema(article_data, img_url, pillar="Market Analysis"):
    """Builds and validates BlogPosting, BreadcrumbList, and FAQPage JSON-LD structured data."""
    headline = (article_data.get("seo_title") or "KeepUpdatedTrend Analysis")[:110]
    description = (article_data.get("meta_description") or article_data.get("intro_paragraph", ""))[:160].strip()

    blog_posting = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": headline,
        "description": description,
        "articleSection": pillar,
        "image": [img_url],
        "author": {
            "@type": "Organization",
            "name": "KeepUpdatedTrend Research",
            "url": SITE_URL
        },
        "publisher": {
            "@type": "Organization",
            "name": "KeepUpdatedTrend",
            "url": SITE_URL
        }
    }

    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": pillar, "item": f"{SITE_URL}/search/label/{pillar.replace(' ', '%20')}"},
            {"@type": "ListItem", "position": 3, "name": headline}
        ]
    }

    schemas = [blog_posting, breadcrumb]

    faqs = article_data.get("faqs", [])
    if faqs:
        faq_entities = []
        for f in faqs:
            if f.get("q") and f.get("a"):
                faq_entities.append({
                    "@type": "Question",
                    "name": f["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": f["a"]}
                })
        if faq_entities:
            schemas.append({
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": faq_entities
            })

    # Validate JSON serialization before deployment
    scripts = []
    for s in schemas:
        if s.get("@type") == "BlogPosting" and (not s.get("headline") or not s.get("description")):
            continue
        scripts.append(f'<script type="application/ld+json">{json.dumps(s)}</script>')

    return "\n".join(scripts)

def audit_onpage_seo(article_data, topic_data, img_url):
    """Validates metadata, headings, internal links, and schema before publication."""
    pillar = topic_data.get("pillar", "Enterprise AI")
    primary_kw = topic_data.get("primary_keyword", "")

    # 1. Ensure clean meta description under 160 chars
    meta_desc = article_data.get("meta_description", "").strip()
    if not meta_desc:
        intro = article_data.get("intro_paragraph", "").split("\n")[0]
        meta_desc = intro[:155].rsplit(" ", 1)[0] + "..."
    article_data["meta_description"] = meta_desc[:160]

    # 2. Generate clean slug
    article_data["slug"] = generate_clean_slug(article_data.get("seo_title", ""), primary_kw)

    # 3. Fetch pillar-matched internal links from SQLite catalogue
    internal_links = find_relevant_internal_links(pillar, primary_kw, limit=3)

    # 4. Generate validated JSON-LD schema block
    schema_html = build_and_validate_schema(article_data, img_url, pillar=pillar)

    return {
        "article_data": article_data,
        "internal_links": internal_links,
        "schema_html": schema_html,
        "seo_passed": bool(article_data.get("seo_title") and len(article_data.get("sections", [])) >= 2)
    }
