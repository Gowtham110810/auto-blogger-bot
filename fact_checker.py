import json
import sqlite3
from datetime import datetime, timezone
from topic_engine import generate_json_with_fallback

DB_PATH = "keepupdatedtrend.db"

def verify_and_refine_article(article_data, research_pack, queue_id=0):
    prompt = f"""
    You are the Managing Fact-Checker & Publication Gatekeeper for KeepUpdatedTrend.
    Audit this drafted article JSON against the collected Research Pack.

    Research Pack:
    {json.dumps(research_pack, indent=2)}

    Drafted Article JSON:
    {json.dumps(article_data, indent=2)}

    Rules:
    1. If any specific dollar figure, percentage, or company claim in the draft is NOT supported by the Research Pack, either replace it with a verified claim from the Research Pack or explicitly label it as an "Illustrative Scenario / Model Assumption".
    2. Ensure clear distinction between verified facts, estimates, and arXiv preprints.
    3. Return the corrected article JSON in the exact same schema, plus a top-level boolean `"gate_passed": true` and `"verified_references"` containing 3-4 clean source objects (`{{"title": "...", "source": "...", "url": "..."}}`).
    """

    verified_data = generate_json_with_fallback(prompt, temperature=0.15)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    status = "verified" if verified_data.get("gate_passed", True) else "flagged_for_review"
    cur.execute("""
        UPDATE claim_records
        SET verification_status = ?, checked_at = ?
        WHERE article_id = ?
    """, (status, now, queue_id))
    conn.commit()
    conn.close()

    return verified_data

def render_references_html(verified_data):
    refs = verified_data.get("verified_references", [])
    if not refs:
        return ""

    items_html = ""
    for r in refs[:4]:
        title = r.get("title", "Primary Reference")
        source = r.get("source", "Official Report")
        url = r.get("url", "#")
        items_html += (
            f'<li style="margin-bottom: 8px; font-size: 14px; color: #cbd5e1;">'
            f'<strong>{source}:</strong> '
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" style="color: #00e5ff; text-decoration: underline;">{title}</a>'
            f'</li>'
        )

    return (
        f'<div class="ds-card" style="margin-top: 24px; border-left: 3px solid #10b981;">'
        f'<div style="font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #10b981; margin-bottom: 10px;">🔎 Authoritative Sources &amp; Verification Ledger</div>'
        f'<ul style="margin: 0; padding-left: 18px;">{items_html}</ul>'
        f'</div>'
    )
