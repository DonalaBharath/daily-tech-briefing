import json
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)
LOOKBACK_HOURS = 30
MAX_PER_SOURCE = 8
MAX_TOTAL = 35

CATEGORY_KEYWORDS = {
    "AI & ML": [
        "ai", "artificial intelligence", "machine learning", "llm",
        "generative ai", "agent", "openai", "gemini", "claude",
        "deep learning", "neural"
    ],
    "Software & Coding": [
        "software", "developer", "programming", "python", "javascript",
        "java", "github", "linux", "database", "framework", "api",
        "open source", "compiler", "developer tools"
    ],
    "Cybersecurity": [
        "cybersecurity", "security", "vulnerability", "cve", "malware",
        "ransomware", "hack", "breach", "zero-day", "phishing"
    ],
    "Cloud & Infrastructure": [
        "cloud", "aws", "azure", "google cloud", "kubernetes", "docker",
        "devops", "server", "datacenter", "infrastructure"
    ],
    "Hardware & Semiconductors": [
        "chip", "semiconductor", "gpu", "cpu", "nvidia", "amd", "intel",
        "qualcomm", "processor", "hardware"
    ],
    "Startups & Business": [
        "startup", "funding", "acquisition", "ipo", "venture", "valuation",
        "launches", "company"
    ],
    "Research & Reports": [
        "research", "paper", "study", "report", "benchmark", "arxiv",
        "scientists", "researchers"
    ]
}

def clean_html(value):
    soup = BeautifulSoup(value or "", "html.parser")
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", unescape(text)).strip()

def parse_date(entry):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            import calendar
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc).astimezone(IST)
    return None

def category(title, summary):
    text = (title + " " + summary).lower()
    scores = {
        name: sum(1 for kw in kws if kw in text)
        for name, kws in CATEGORY_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "Technology"

def relevance(title, summary):
    text = (title + " " + summary).lower()
    important = [
        "launch", "released", "release", "announced", "acquisition",
        "security", "vulnerability", "breach", "research", "funding",
        "new model", "update", "major", "open source", "benchmark"
    ]
    return sum(2 for x in important if x in text) + min(len(summary) // 250, 3)

def fetch():
    with open("config/sources.json", encoding="utf-8") as f:
        sources = json.load(f)["feeds"]

    cutoff = NOW - timedelta(hours=LOOKBACK_HOURS)
    items = []

    headers = {"User-Agent": "DailyTechBriefing/1.0"}

    for source in sources:
        try:
            response = requests.get(source["url"], headers=headers, timeout=20)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            count = 0
            for entry in feed.entries:
                if count >= MAX_PER_SOURCE:
                    break

                title = clean_html(entry.get("title", ""))
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                link = entry.get("link", "")
                published = parse_date(entry)

                if not title or not link:
                    continue
                if published and published < cutoff:
                    continue

                items.append({
                    "source": source["name"],
                    "title": title,
                    "summary": summary[:900],
                    "link": link,
                    "published": published or NOW,
                    "category": category(title, summary),
                    "score": relevance(title, summary)
                })
                count += 1

        except Exception as exc:
            print(f"Source failed: {source['name']}: {exc}")

    # Deduplicate by normalized title.
    seen = set()
    unique = []
    for item in sorted(items, key=lambda x: (x["score"], x["published"]), reverse=True):
        key = re.sub(r"[^a-z0-9]+", " ", item["title"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique[:MAX_TOTAL]

def summarize_fallback(item):
    summary = item["summary"]
    if not summary:
        return "A new technology development was reported. See the source for details."
    sentences = re.split(r"(?<=[.!?])\s+", summary)
    return " ".join(sentences[:2])[:450]

def build_html(items):
    grouped = {}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)

    sections = []
    for cat, cat_items in grouped.items():
        blocks = []
        for i, item in enumerate(cat_items[:6], 1):
            summary = summarize_fallback(item)
            blocks.append(f"""
            <div style="margin:0 0 22px 0;">
              <div style="font-size:17px;font-weight:700;margin-bottom:6px;">
                {i}. {item['title']}
              </div>
              <div style="font-size:14px;line-height:1.55;">
                <b>What happened:</b> {summary}
              </div>
              <div style="font-size:13px;margin-top:6px;">
                <b>Source:</b> {item['source']} ·
                <a href="{item['link']}">Read source</a>
              </div>
            </div>
            """)
        sections.append(f"""
        <h2 style="font-size:19px;margin:28px 0 14px 0;">{cat}</h2>
        {''.join(blocks)}
        """)

    top = items[:3]
    top_html = "".join(
        f"<li style='margin-bottom:8px;'><a href='{x['link']}'>{x['title']}</a></li>"
        for x in top
    )

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:760px;margin:auto;color:#222;">
      <h1>📰 Daily Tech Brief — {NOW.strftime('%d %B %Y')}</h1>
      <p>Good morning! Here are the most relevant technology developments collected from the configured sources.</p>

      <h2>🔥 3 things to know first</h2>
      <ol>{top_html}</ol>

      {''.join(sections)}

      <hr>
      <p style="font-size:12px;color:#666;">
        Automated briefing. Items are selected from RSS feeds published during the recent lookback period.
        Always open the original source for full context.
      </p>
    </body></html>
    """

def send_email(html, count):
    username = os.environ["GMAIL_USERNAME"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["TO_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 Daily Tech Brief — {NOW.strftime('%d %b %Y')} ({count} updates)"
    msg["From"] = username
    msg["To"] = recipient

    plain = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls(context=context)
        server.login(username, password)
        server.sendmail(username, recipient, msg.as_string())

def main():
    items = fetch()
    if not items:
        raise RuntimeError("No recent stories were collected. Check RSS sources/network.")
    html = build_html(items)
    send_email(html, len(items))
    print(f"Sent briefing with {len(items)} updates.")

if __name__ == "__main__":
    main()
