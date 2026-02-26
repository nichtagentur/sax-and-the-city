#!/usr/bin/env python3
"""
Sax & The City -- AI Email Assistant
Monitors the ai-assistent@nichtagentur.at inbox for emails from Tanja.
When an email arrives, uses Claude to figure out what she wants and acts on it.
Replies by email with what was done.
"""

import imaplib
import email
import email.header
import smtplib
import os
import sys
import time
import json
import subprocess
import logging
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = PROJECT_DIR / "content"
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Import article generation functions from the existing script
sys.path.insert(0, str(SCRIPT_DIR))
from generate_article import (
    get_anthropic_client,
    generate_article_text,
    translate_article,
    generate_featured_image,
    create_hugo_page,
    build_front_matter,
    load_plan,
    save_plan,
    get_next_topic,
    SITE_URL,
)

# Email config
IMAP_HOST = "mail.easyname.eu"
IMAP_PORT = 993
SMTP_HOST = "mail.easyname.eu"
SMTP_PORT = 587
EMAIL_USER = "i-am-a-user@nichtagentur.at"
EMAIL_PASS = os.environ.get("SMTP_PASS", "i_am_an_AI_password_2026")
EMAIL_DISPLAY = "Sax & The City AI Editor <i-am-a-user@nichtagentur.at>"
ALLOWED_SENDER = "tanja.wassermair@geogebra.org"

# Polling interval
POLL_INTERVAL = 30  # seconds

# Tracks which emails we already replied to (survives crashes)
PROCESSED_FILE = LOG_DIR / "processed_emails.json"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "email_assistant.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("email_assistant")


def load_processed():
    """Load set of Message-IDs we already replied to."""
    if PROCESSED_FILE.exists():
        return set(json.loads(PROCESSED_FILE.read_text()))
    return set()


def save_processed(processed):
    """Save set of processed Message-IDs."""
    # Keep only last 500 to avoid unbounded growth
    recent = sorted(processed)[-500:]
    PROCESSED_FILE.write_text(json.dumps(recent, indent=2))


def connect_imap():
    """Connect to IMAP server and select inbox."""
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=30)
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select("INBOX")
    return mail


def check_for_emails(mail):
    """Check for recent emails from the allowed sender that we haven't replied to yet.
    Uses Message-ID tracking so read-but-unprocessed emails are not lost.
    Only searches emails from the last 3 days to keep polling fast."""
    results = []
    processed = load_processed()
    try:
        # Search only recent emails from Tanja (last 3 days) to keep it fast
        since_date = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        status, data = mail.search(
            None, '(FROM "{}" SINCE {})'.format(ALLOWED_SENDER, since_date)
        )
        if status != "OK" or not data[0]:
            return results

        email_ids = data[0].split()
        for eid in email_ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Check Message-ID -- skip if already processed
            message_id = msg.get("Message-ID", "").strip()
            if message_id in processed:
                continue

            # Decode subject
            subject_parts = email.header.decode_header(msg["Subject"] or "")
            subject = ""
            for part, charset in subject_parts:
                if isinstance(part, bytes):
                    subject += part.decode(charset or "utf-8", errors="replace")
                else:
                    subject += part

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")

            # Do NOT mark as seen -- the Message-ID tracker handles dedup.
            # Marking seen before processing causes lost emails on crash.

            results.append((message_id, subject.strip(), body.strip()))
            log.info(f"Found email: '{subject.strip()}'")

    except Exception as e:
        log.error(f"Error checking emails: {e}")

    return results


def classify_email(subject, body):
    """Use Claude to classify the email into an action + extract details."""
    client = get_anthropic_client()

    # Count current articles
    article_count = 0
    sections_count = {}
    for section_dir in CONTENT_DIR.iterdir():
        if section_dir.is_dir() and not section_dir.name.startswith("_"):
            for article_dir in section_dir.iterdir():
                if article_dir.is_dir() and (article_dir / "index.md").exists():
                    article_count += 1
                    sec = section_dir.name
                    sections_count[sec] = sections_count.get(sec, 0) + 1

    plan = load_plan()
    pending = [t for t in plan["topics"] if t["status"] == "pending"]
    done = [t for t in plan["topics"] if t["status"] == "done"]

    prompt = f"""You are the AI editor of the saxophone blog "Sax & The City".
You received an email from Tanja (the blog owner).

EMAIL SUBJECT: {subject}
EMAIL BODY:
{body}

BLOG STATUS:
- Published articles: {article_count} total across sections: {json.dumps(sections_count)}
- Completed topics: {len(done)}
- Pending topics in plan: {len(pending)}
- Pending topic titles: {json.dumps([t['title'] for t in pending])}
- Done topic slugs: {json.dumps([t['slug'] for t in done])}
- Site URL: {SITE_URL}

Classify what Tanja wants into exactly ONE of these actions:

1. "create" -- She wants a NEW article written on a specific topic she describes.
   Return: {{"action": "create", "title": "...", "section": "one of: getting-started, practice-room, improvisation, gear-guide, music-theory", "summary": "one sentence summary", "tags": ["tag1", "tag2"], "image_prompt": "description for image generation"}}

2. "edit" -- She wants to CHANGE an existing article.
   Return: {{"action": "edit", "slug": "the-article-slug", "instructions": "what to change"}}

3. "generate_next" -- She wants to publish the next planned article from the content plan.
   Return: {{"action": "generate_next"}}

4. "answer" -- She is asking a question or wants info, no blog changes needed.
   Return: {{"action": "answer", "response": "your helpful answer to her question"}}

Return ONLY valid JSON, nothing else."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Extract JSON from response (handle markdown code blocks)
    if "```" in text:
        text = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL).group(1).strip()

    return json.loads(text)


def handle_create(data):
    """Create a new article based on Tanja's request."""
    topic = {
        "slug": re.sub(r"[^a-z0-9]+", "-", data["title"].lower()).strip("-"),
        "title": data["title"],
        "section": data.get("section", "getting-started"),
        "tags": data.get("tags", []),
        "image_prompt": data.get("image_prompt", f"Saxophone related to {data['title']}, professional photography"),
        "summary": data.get("summary", data["title"]),
        "status": "pending",
    }

    log.info(f"Creating article: {topic['title']}")

    # Add to plan
    plan = load_plan()
    plan["topics"].append(topic)
    save_plan(plan)

    # Generate content
    log.info("  Generating English article...")
    article_en = generate_article_text(topic, lang="en")
    log.info("  Translating to German...")
    article_de = translate_article(article_en, topic)
    log.info("  Generating featured image...")
    image = generate_featured_image(topic)
    log.info("  Creating Hugo page...")
    create_hugo_page(topic, article_en, article_de, image)

    # Mark done
    topic["status"] = "done"
    save_plan(plan)

    # Git commit and push
    git_push(f"New article: {topic['title']}")

    article_url = f"{SITE_URL}/{topic['section']}/{topic['slug']}/"
    article_url_de = f"{SITE_URL}/de/{topic['section']}/{topic['slug']}/"

    return (
        f"Done! I created a new article:\n\n"
        f"Title: {topic['title']}\n"
        f"Section: {topic['section']}\n\n"
        f"English: {article_url}\n"
        f"German: {article_url_de}\n\n"
        f"The article is published and will be live in about a minute."
    )


def handle_edit(data):
    """Edit an existing article based on instructions."""
    slug = data["slug"]
    instructions = data["instructions"]

    # Find the article
    article_path = None
    for section_dir in CONTENT_DIR.iterdir():
        if section_dir.is_dir():
            candidate = section_dir / slug / "index.md"
            if candidate.exists():
                article_path = candidate
                break

    if not article_path:
        return f"I could not find an article with the slug '{slug}'. Please check the article name and try again."

    log.info(f"Editing article: {slug}")

    # Read current content
    content = article_path.read_text()
    parts = content.split("---", 2)
    if len(parts) >= 3:
        front_matter = parts[1]
        article_text = parts[2].strip()
    else:
        return "Could not parse the article format."

    # Use Claude to edit
    client = get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"""You are editing an existing saxophone blog article. Apply the following changes:

INSTRUCTIONS FROM THE BLOG OWNER:
{instructions}

CURRENT ARTICLE TEXT (markdown, without front matter):
{article_text}

Return ONLY the updated article text in markdown. Keep the same structure and style. Do NOT include front matter.""",
            }
        ],
    )
    new_text_en = response.content[0].text.strip()

    # Save English
    article_path.write_text(f"---{front_matter}---\n\n{new_text_en}\n")
    log.info("  English version updated")

    # Find and get topic info for translation
    plan = load_plan()
    topic = None
    for t in plan["topics"]:
        if t["slug"] == slug:
            topic = t
            break

    # Re-translate German version
    de_path = article_path.parent / "index.de.md"
    if de_path.exists() and topic:
        log.info("  Re-translating German version...")
        new_text_de = translate_article(new_text_en, topic)
        de_content = de_path.read_text()
        de_parts = de_content.split("---", 2)
        if len(de_parts) >= 3:
            de_path.write_text(f"---{de_parts[1]}---\n\n{new_text_de}\n")
            log.info("  German version updated")

    git_push(f"Edited article: {slug}")

    section = article_path.parent.parent.name
    article_url = f"{SITE_URL}/{section}/{slug}/"
    return (
        f"Done! I updated the article '{slug}'.\n\n"
        f"Changes applied: {instructions}\n\n"
        f"Link: {article_url}\n\n"
        f"Both English and German versions are updated. Changes will be live in about a minute."
    )


def handle_generate_next(data):
    """Generate the next article from the content plan."""
    plan = load_plan()
    topic = get_next_topic(plan)

    if not topic:
        return "All planned articles have been published! There are no more pending topics in the content plan. Send me a topic if you want a new article."

    log.info(f"Generating next planned article: {topic['title']}")

    log.info("  Generating English article...")
    article_en = generate_article_text(topic, lang="en")
    log.info("  Translating to German...")
    article_de = translate_article(article_en, topic)
    log.info("  Generating featured image...")
    image = generate_featured_image(topic)
    log.info("  Creating Hugo page...")
    create_hugo_page(topic, article_en, article_de, image)

    topic["status"] = "done"
    save_plan(plan)

    git_push(f"New article: {topic['title']}")

    article_url = f"{SITE_URL}/{topic['section']}/{topic['slug']}/"
    article_url_de = f"{SITE_URL}/de/{topic['section']}/{topic['slug']}/"

    return (
        f"Done! I published the next planned article:\n\n"
        f"Title: {topic['title']}\n"
        f"Section: {topic['section']}\n"
        f"Summary: {topic['summary']}\n\n"
        f"English: {article_url}\n"
        f"German: {article_url_de}\n\n"
        f"The article will be live in about a minute."
    )


def handle_answer(data):
    """Just return the AI's answer -- no blog changes."""
    return data.get("response", "I'm not sure how to answer that. Could you rephrase?")


def git_push(commit_message):
    """Commit and push changes to GitHub."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=PROJECT_DIR, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "push"], cwd=PROJECT_DIR, check=True, capture_output=True)
        log.info(f"  Git: committed and pushed -- '{commit_message}'")
    except subprocess.CalledProcessError as e:
        log.warning(f"  Git push issue: {e.stderr.decode() if e.stderr else e}")


def send_reply(to_addr, subject, body):
    """Send a reply email. Returns True on success, False on failure."""
    msg = MIMEMultipart()
    msg["From"] = EMAIL_DISPLAY
    msg["To"] = to_addr
    msg["Subject"] = f"Re: {subject}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_addr, msg.as_string())
        log.info(f"Reply sent to {to_addr}")
        return True
    except Exception as e:
        log.error(f"Failed to send reply: {e}")
        return False


def process_email(subject, body):
    """Classify and handle one email."""
    log.info(f"Processing email: '{subject}'")

    try:
        classification = classify_email(subject, body)
        action = classification.get("action", "answer")
        log.info(f"  Classified as: {action}")

        if action == "create":
            result = handle_create(classification)
        elif action == "edit":
            result = handle_edit(classification)
        elif action == "generate_next":
            result = handle_generate_next(classification)
        else:
            result = handle_answer(classification)

        return result

    except SystemExit as e:
        log.error(f"SystemExit caught (likely missing API key): {e}", exc_info=True)
        return "Sorry, the AI service is temporarily unavailable (API key issue). Please try again later."
    except Exception as e:
        log.error(f"Error processing email: {e}", exc_info=True)
        return f"Sorry, something went wrong while processing your request. Error: {str(e)}\n\nPlease try again or rephrase your request."


def startup_self_test():
    """Run quick checks at startup so misconfigurations are obvious in logs."""
    log.info("--- Startup self-test ---")

    # Test IMAP connection
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=15)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.logout()
        log.info("  IMAP login: PASS")
    except Exception as e:
        log.error(f"  IMAP login: FAIL -- {e}")

    # Check Claude API key
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY_1")
    if api_key:
        log.info("  Claude API key: PASS (key present)")
    else:
        log.error("  Claude API key: FAIL (no ANTHROPIC_API_KEY or CLAUDE_API_KEY_1 in environment)")

    log.info("--- Self-test complete ---")


def main():
    """Main polling loop."""
    log.info("=" * 60)
    log.info("Sax & The City Email Assistant starting up")
    log.info(f"Monitoring: {EMAIL_USER}")
    log.info(f"Accepting emails from: {ALLOWED_SENDER}")
    log.info(f"Poll interval: {POLL_INTERVAL}s")
    log.info("=" * 60)

    startup_self_test()

    poll_count = 0
    while True:
        try:
            mail = connect_imap()
            emails = check_for_emails(mail)

            poll_count += 1
            log.info(f"Poll #{poll_count}: checked, {len(emails)} new")

            processed = load_processed()
            for message_id, subject, body in emails:
                result = process_email(subject, body)
                sent_ok = send_reply(ALLOWED_SENDER, subject, result)
                if sent_ok:
                    # Only mark as processed AFTER reply was actually sent
                    processed.add(message_id)
                    save_processed(processed)
                    log.info(f"  Marked as processed: {message_id}")
                else:
                    log.warning(f"  Reply failed -- will retry next poll: {message_id}")

            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

        except Exception as e:
            poll_count += 1
            log.error(f"Poll #{poll_count}: connection error -- {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
