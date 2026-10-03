# Daily Tech Briefing

A GitHub Actions workflow that collects recent technology news from RSS feeds, creates a concise daily briefing, and emails it.

## Schedule

Runs every day at **8:00 AM Asia/Kolkata (IST)**.

## Free setup

This version uses:
- GitHub Actions for scheduling
- RSS feeds for news collection
- Gmail SMTP for email delivery
- No Superhuman subscription

### 1. Create a GitHub repository

Create a new repository, for example:

`daily-tech-briefing`

Upload all files from this project.

### 2. Create a Gmail App Password

For Gmail SMTP, use a Google App Password rather than your normal Gmail password.

Your Google account needs 2-Step Verification enabled. Then create an App Password and copy the generated 16-character password.

### 3. Add GitHub Secrets

Repository → Settings → Secrets and variables → Actions → New repository secret.

Add:

`GMAIL_USERNAME` = your Gmail address

`GMAIL_APP_PASSWORD` = your Gmail App Password

`TO_EMAIL` = email address where the briefing should be delivered

### 4. Enable Actions

Open the Actions tab and enable workflows if GitHub asks.

You can test it manually:
Actions → Daily Tech Briefing → Run workflow.

## Important

GitHub scheduled workflows are not guaranteed to start at exactly the minute requested. The workflow is configured for 8:00 AM IST, but GitHub may delay scheduled jobs during periods of high load.

The workflow uses RSS feeds and does not crawl every webpage on the internet. Add or remove feeds in `config/sources.json`.

## Sources

The default source list includes major technology publications and research feeds. The workflow filters recent items and produces a concise briefing.

"# daily-tech-briefing" 
