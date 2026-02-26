#!/usr/bin/env python3
"""
Sax & The City -- AI Article Generator
Generates SEO-optimized saxophone articles with AI-generated images.
Uses Claude Sonnet for text and Imagen for featured images.
Sends email notification after each article is published.
"""

import json
import os
import sys
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = PROJECT_DIR / "content"
PLAN_FILE = SCRIPT_DIR / "content_plan.json"

# Site URL
SITE_URL = "https://nichtagentur.github.io/sax-and-the-city"

# Email settings
NOTIFY_EMAIL = "tanja.wassermair@geogebra.org"
SMTP_HOST = "mail.easyname.eu"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "i-am-a-user@nichtagentur.at")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
FROM_EMAIL = "i-am-a-user@nichtagentur.at"


def load_plan():
    with open(PLAN_FILE) as f:
        return json.load(f)


def save_plan(plan):
    with open(PLAN_FILE, "w") as f:
        json.dump(plan, f, indent=2)


def get_next_topic(plan):
    """Get the next pending topic from the content plan."""
    for topic in plan["topics"]:
        if topic["status"] == "pending":
            return topic
    return None


def send_notification_email(topic, article_text):
    """Send email notification about a newly published article."""
    password = SMTP_PASS or os.environ.get("SMTP_PASS", "")
    if not password:
        print("  WARNING: No SMTP password set, skipping email notification")
        return False

    article_url = f"{SITE_URL}/{topic['section']}/{topic['slug']}/"
    # Get first ~300 chars as preview
    preview = article_text[:300].strip()
    if len(article_text) > 300:
        preview += "..."

    subject = f"New article published: {topic['title']}"

    body = f"""Hi Tanja,

A new article has been published on Sax & The City!

Title: {topic['title']}
Category: {topic['section'].replace('-', ' ').title()}
Summary: {topic['summary']}

Preview:
{preview}

Read the full article: {article_url}

-- Sax & The City (automated notification)
"""

    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, password)
            server.sendmail(FROM_EMAIL, NOTIFY_EMAIL, msg.as_string())
        print(f"  Email sent to {NOTIFY_EMAIL}")
        return True
    except Exception as e:
        print(f"  WARNING: Failed to send email: {e}")
        return False


def generate_article_text(topic):
    """Generate article text using Claude Sonnet."""
    import anthropic

    api_key = os.environ.get("CLAUDE_API_KEY_1") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No Anthropic API key found")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are an experienced saxophone teacher with 20+ years of playing and teaching experience. You run "Sax & The City", a blog where you share practical knowledge with beginners and intermediate players.

Write an article based on these details:

ARTICLE:
- Title: {topic['title']}
- Category: {topic['section'].replace('-', ' ').title()}
- Summary: {topic['summary']}
- Target tags: {', '.join(topic['tags'])}

VOICE & TONE:
- Write as a real teacher sharing personal experience. Use "I" and "you" naturally.
- Share specific anecdotes: "When I was learning altissimo, my teacher Larry Teal told me..." or "I spent three months struggling with this until..."
- Be warm and encouraging, but also honest about challenges.
- Vary your sentence structure. Mix short punchy sentences with longer explanatory ones.
- NO generic AI patterns: never write "Here are 5 tips...", "In conclusion...", "Let's dive in...", "Whether you're a beginner or advanced..."

CONTENT REQUIREMENTS (E-E-A-T signals for Google quality):

1. REAL REFERENCES: Name specific real musicians, recordings, gear models, and method books. Examples:
   - Musicians: Charlie Parker, Cannonball Adderley, Michael Brecker, Kenny Garrett, Branford Marsalis
   - Recordings: "Kind of Blue", "Giant Steps", specific tracks
   - Gear: Yamaha YAS-280, Selmer Mark VI, Vandoren V16 mouthpiece, Rico Royal #2.5 reeds
   - Books: "The Art of Saxophone Playing" by Larry Teal, "Top Tones for the Saxophone" by Sigurd Rascher

2. FROM THE PRACTICE ROOM: Include a section called "## From the Practice Room" with 2-3 specific, unique practice tips that go beyond generic advice. Things a real teacher would share in a lesson.

3. WATCH OUT FOR: Include a section called "## Common Mistakes to Avoid" with 3-4 specific pitfalls and how to fix them.

4. SOURCES: End with a section called "## Further Reading & Sources" listing 3-5 real, authoritative resources (books, educational websites, masterclass videos). Format as a simple list.

5. FAQ: Include "## Frequently Asked Questions" with 3 questions using ### for each question.

LENGTH: 800-1,200 words. Be concise and scannable. Every paragraph should earn its place.

FORMAT RULES:
- Return ONLY the article body in Markdown (no title -- that goes in front matter)
- Start directly with an engaging introduction paragraph
- Do NOT include the title as an H1 heading
- Use ## for main sections and ### for subsections
- Include a brief "Key Takeaway" blockquote (>) near the top -- one or two sentences max
- Do NOT use emoji
- No keyword stuffing
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


def generate_featured_image(topic):
    """Generate featured image using Imagen via Gemini API."""
    from google import genai
    from google.genai import types
    from PIL import Image

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("WARNING: No Gemini API key found, skipping image generation")
        return None

    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=f"{topic['image_prompt']}, professional photography, high quality, 16:9 aspect ratio",
            config=types.GenerateImagesConfig(
                number_of_images=1,
            ),
        )

        for img_data in response.generated_images:
            img = Image.open(BytesIO(img_data.image.image_bytes))
            return img

    except Exception as e:
        print(f"WARNING: Image generation failed: {e}")
        return None


def create_hugo_page(topic, article_text, image):
    """Create a Hugo page bundle with the article and featured image."""
    from PIL import Image

    section = topic["section"]
    slug = topic["slug"]
    bundle_dir = CONTENT_DIR / section / slug
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Save featured image
    if image:
        image_path = bundle_dir / "featured.jpg"
        # Resize to reasonable web size
        if image.width > 1600:
            ratio = 1600 / image.width
            new_size = (1600, int(image.height * ratio))
            image = image.resize(new_size, Image.LANCZOS)
        image.save(image_path, "JPEG", quality=85)
        print(f"  Image saved: {image_path}")

    # Calculate a reasonable date (spread articles across recent weeks)
    now = datetime.now()
    front_matter = {
        "title": topic["title"],
        "date": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "lastmod": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "draft": False,
        "summary": topic["summary"],
        "tags": topic["tags"],
        "categories": [topic["section"].replace("-", " ").title()],
    }

    if image:
        front_matter["featureimage"] = "featured.jpg"

    # Build front matter as YAML
    fm_lines = ["---"]
    fm_lines.append(f'title: "{front_matter["title"]}"')
    fm_lines.append(f'date: {front_matter["date"]}')
    fm_lines.append(f'lastmod: {front_matter["lastmod"]}')
    fm_lines.append(f'draft: {str(front_matter["draft"]).lower()}')
    fm_lines.append(f'summary: "{front_matter["summary"]}"')
    fm_lines.append("tags:")
    for tag in front_matter["tags"]:
        fm_lines.append(f'  - "{tag}"')
    fm_lines.append("categories:")
    for cat in front_matter["categories"]:
        fm_lines.append(f'  - "{cat}"')
    if image:
        fm_lines.append('image: "featured.jpg"')
    fm_lines.append("authors:")
    fm_lines.append('  - "Sax & The City"')
    fm_lines.append("showTableOfContents: true")
    fm_lines.append("---")

    content = "\n".join(fm_lines) + "\n\n" + article_text + "\n"

    index_path = bundle_dir / "index.md"
    with open(index_path, "w") as f:
        f.write(content)
    print(f"  Article saved: {index_path}")

    return index_path


def main():
    """Generate the next article from the content plan."""
    # Check for specific topic slug as argument
    target_slug = None
    count = 1
    if len(sys.argv) > 1:
        if sys.argv[1].isdigit():
            count = int(sys.argv[1])
        else:
            target_slug = sys.argv[1]

    plan = load_plan()

    for i in range(count):
        if target_slug:
            topic = None
            for t in plan["topics"]:
                if t["slug"] == target_slug:
                    topic = t
                    break
            if not topic:
                print(f"ERROR: Topic '{target_slug}' not found in content plan")
                sys.exit(1)
        else:
            topic = get_next_topic(plan)

        if not topic:
            print("All topics have been generated! Add more to content_plan.json.")
            break

        print(f"\n[{i+1}/{count}] Generating: {topic['title']}")
        print(f"  Section: {topic['section']}")

        # Generate text
        print("  Writing article with Claude...")
        article_text = generate_article_text(topic)
        print(f"  Article generated ({len(article_text)} chars)")

        # Generate image
        print("  Generating featured image...")
        image = generate_featured_image(topic)

        # Create Hugo page bundle
        create_hugo_page(topic, article_text, image)

        # Send email notification
        print("  Sending email notification...")
        send_notification_email(topic, article_text)

        # Mark as done
        topic["status"] = "done"
        save_plan(plan)
        print(f"  Done! Topic marked as completed.")

    print(f"\nFinished generating {count} article(s).")


if __name__ == "__main__":
    main()
