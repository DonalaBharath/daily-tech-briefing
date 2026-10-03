import base64
import calendar
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape, unescape

import feedparser
import requests
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)

LOOKBACK_HOURS = 30
MAX_PER_SOURCE = 8
MAX_TOTAL = 35

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


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
            return datetime.fromtimestamp(
                calendar.timegm(value),
                tz=timezone.utc
            ).astimezone(IST)

    return None


def category(title, summary):
    text = (title + " " + summary).lower()

    scores = {
        name: sum(1 for kw in keywords if kw in text)
        for name, keywords in CATEGORY_KEYWORDS.items()
    }

    best = max(scores, key=scores.get)

    return best if scores[best] else "Technology"


def relevance(title, summary):
    text = (title + " " + summary).lower()

    important = [
        "launch",
        "released",
        "release",
        "announced",
        "acquisition",
        "security",
        "vulnerability",
        "breach",
        "research",
        "funding",
        "new model",
        "update",
        "major",
        "open source",
        "benchmark"
    ]

    return (
        sum(2 for x in important if x in text)
        + min(len(summary) // 250, 3)
    )


def fetch():
    with open("config/sources.json", encoding="utf-8") as f:
        sources = json.load(f)["feeds"]

    cutoff = NOW - timedelta(hours=LOOKBACK_HOURS)

    items = []

    headers = {
        "User-Agent": "DailyTechBriefing/1.0"
    }

    for source in sources:
        try:
            response = requests.get(
                source["url"],
                headers=headers,
                timeout=20
            )

            response.raise_for_status()

            feed = feedparser.parse(response.content)

            count = 0

            for entry in feed.entries:

                if count >= MAX_PER_SOURCE:
                    break

                title = clean_html(entry.get("title", ""))

                summary = clean_html(
                    entry.get(
                        "summary",
                        entry.get("description", "")
                    )
                )

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
            print(
                f"Source failed: {source['name']}: {exc}"
            )

    # Deduplicate by normalized title.
    seen = set()
    unique = []

    for item in sorted(
        items,
        key=lambda x: (x["score"], x["published"]),
        reverse=True
    ):

        key = re.sub(
            r"[^a-z0-9]+",
            " ",
            item["title"].lower()
        ).strip()

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique[:MAX_TOTAL]


def summarize_fallback(item):
    summary = item["summary"]

    if not summary:
        return (
            "A new technology development was reported. "
            "See the source for details."
        )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        summary
    )

    return " ".join(sentences[:2])[:450]


def build_html(items):
    grouped = {}

    for item in items:
        grouped.setdefault(
            item["category"],
            []
        ).append(item)

    sections = []

    for cat, cat_items in grouped.items():

        blocks = []

        for i, item in enumerate(cat_items[:6], 1):

            summary = summarize_fallback(item)

            title = escape(item["title"])
            source = escape(item["source"])
            link = escape(item["link"], quote=True)
            summary = escape(summary)

            blocks.append(
                f"""
                <div style="margin:0 0 22px 0;">

                    <div style="
                        font-size:17px;
                        font-weight:700;
                        margin-bottom:6px;
                    ">
                        {i}. {title}
                    </div>

                    <div style="
                        font-size:14px;
                        line-height:1.55;
                    ">
                        <b>What happened:</b> {summary}
                    </div>

                    <div style="
                        font-size:13px;
                        margin-top:6px;
                    ">
                        <b>Source:</b> {source} ·
                        <a href="{link}">Read source</a>
                    </div>

                </div>
                """
            )

        sections.append(
            f"""
            <h2 style="
                font-size:19px;
                margin:28px 0 14px 0;
            ">
                {escape(cat)}
            </h2>

            {''.join(blocks)}
            """
        )

    top = items[:3]

    top_html = "".join(
        f"""
        <li style="margin-bottom:8px;">
            <a href="{escape(x['link'], quote=True)}">
                {escape(x['title'])}
            </a>
        </li>
        """
        for x in top
    )

    return f"""
    <html>
    <body style="
        font-family:Arial,sans-serif;
        max-width:760px;
        margin:auto;
        color:#222;
    ">

        <h1>
            📰 Daily Tech Brief —
            {NOW.strftime('%d %B %Y')}
        </h1>

        <p>
            Good morning! Here are the most relevant
            technology developments collected from
            the configured sources.
        </p>

        <h2>🔥 3 things to know first</h2>

        <ol>
            {top_html}
        </ol>

        {''.join(sections)}

        <hr>

        <p style="
            font-size:12px;
            color:#666;
        ">
            Automated briefing. Items are selected
            from RSS feeds published during the recent
            lookback period. Always open the original
            source for full context.
        </p>

    </body>
    </html>
    """


def get_gmail_service():
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    refresh_token = os.environ["GMAIL_REFRESH_TOKEN"]

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[GMAIL_SEND_SCOPE]
    )

    if not credentials.valid:
        credentials.refresh(Request())

    return build(
        "gmail",
        "v1",
        credentials=credentials
    )


def send_email(html, count):
    recipient = os.environ["TO_EMAIL"]

    subject = (
        f"📰 Daily Tech Brief — "
        f"{NOW.strftime('%d %b %Y')} "
        f"({count} updates)"
    )

    plain = BeautifulSoup(
        html,
        "html.parser"
    ).get_text(
        "\n",
        strip=True
    )

    message = MIMEMultipart("alternative")

    message["To"] = recipient
    message["Subject"] = subject

    message.attach(
        MIMEText(
            plain,
            "plain",
            "utf-8"
        )
    )

    message.attach(
        MIMEText(
            html,
            "html",
            "utf-8"
        )
    )

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    service = get_gmail_service()

    service.users().messages().send(
        userId="me",
        body={
            "raw": raw_message
        }
    ).execute()

    print(
        f"Gmail API: email sent successfully to {recipient}"
    )


def main():
    print("Starting Daily Tech Briefing...")

    items = fetch()

    if not items:
        raise RuntimeError(
            "No recent stories were collected. "
            "Check RSS sources/network."
        )

    print(
        f"Collected {len(items)} technology updates."
    )

    html = build_html(items)

    send_email(
        html,
        len(items)
    )

    print(
        f"Daily briefing sent with {len(items)} updates."
    )


if __name__ == "__main__":
    main()