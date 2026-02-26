#!/usr/bin/env python3
"""
Sax & The City -- AI Article Generator
Generates SEO-optimized saxophone articles in English and German.
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

# German section name mapping
SECTION_NAMES_DE = {
    "getting-started": "Einstieg",
    "practice-room": "Ueberaum",
    "improvisation": "Improvisation",
    "gear-guide": "Equipment",
    "music-theory": "Musiktheorie",
}


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


def get_anthropic_client():
    """Get an Anthropic client with API key."""
    import anthropic

    api_key = os.environ.get("CLAUDE_API_KEY_1") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No Anthropic API key found")
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def send_notification_email(topic, article_text):
    """Send email notification about a newly published article."""
    password = SMTP_PASS or os.environ.get("SMTP_PASS", "")
    if not password:
        print("  WARNING: No SMTP password set, skipping email notification")
        return False

    article_url_en = f"{SITE_URL}/{topic['section']}/{topic['slug']}/"
    article_url_de = f"{SITE_URL}/de/{topic['section']}/{topic['slug']}/"
    preview = article_text[:300].strip()
    if len(article_text) > 300:
        preview += "..."

    subject = f"New article published: {topic['title']}"

    body = f"""Hi Tanja,

A new article has been published on Sax & The City (in English and German)!

Title: {topic['title']}
Category: {topic['section'].replace('-', ' ').title()}
Summary: {topic['summary']}

Preview:
{preview}

English: {article_url_en}
German: {article_url_de}

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


def generate_article_text(topic, lang="en"):
    """Generate article text using Claude Sonnet in the specified language."""
    client = get_anthropic_client()

    if lang == "de":
        prompt = f"""Du bist ein erfahrener Saxophonlehrer mit ueber 20 Jahren Spiel- und Unterrichtserfahrung. Du betreibst "Sax & The City", einen Blog, auf dem du praktisches Wissen mit Anfaengern und fortgeschrittenen Spielern teilst.

Schreibe einen Artikel basierend auf diesen Details:

ARTIKEL:
- Titel: {topic['title']}
- Kategorie: {SECTION_NAMES_DE.get(topic['section'], topic['section'])}
- Zusammenfassung: {topic['summary']}
- Ziel-Tags: {', '.join(topic['tags'])}

STIMME & TON:
- Schreibe als echter Lehrer, der persoenliche Erfahrungen teilt. Verwende "ich" und "du" natuerlich.
- Teile konkrete Anekdoten: "Als ich Altissimo lernte, sagte mir mein Lehrer..." oder "Ich habe drei Monate damit gekaempft, bis..."
- Sei warm und ermutigend, aber auch ehrlich ueber Herausforderungen.
- Variiere deine Satzstruktur. Mische kurze praegnante Saetze mit laengeren erklaerenden.
- KEINE generischen KI-Muster: schreibe nie "Hier sind 5 Tipps...", "Zusammenfassend...", "Tauchen wir ein...", "Egal ob Anfaenger oder Fortgeschrittener..."

INHALTLICHE ANFORDERUNGEN (E-E-A-T-Signale fuer Google-Qualitaet):

1. ECHTE REFERENZEN: Nenne konkrete echte Musiker, Aufnahmen, Equipment-Modelle und Lehrbuecher.
   - Musiker: Charlie Parker, Cannonball Adderley, Michael Brecker, Kenny Garrett, Branford Marsalis
   - Aufnahmen: "Kind of Blue", "Giant Steps", konkrete Stuecke
   - Equipment: Yamaha YAS-280, Selmer Mark VI, Vandoren V16 Mundstueck, Rico Royal #2.5 Blaetter
   - Buecher: "The Art of Saxophone Playing" von Larry Teal, "Top Tones for the Saxophone" von Sigurd Rascher

2. AUS DEM UEBERAUM: Fuege einen Abschnitt "## Aus dem Ueberaum" mit 2-3 spezifischen, einzigartigen Uebetipps ein, die ueber generische Ratschlaege hinausgehen.

3. AUFGEPASST: Fuege einen Abschnitt "## Haeufige Fehler vermeiden" mit 3-4 konkreten Fallstricken und wie man sie behebt ein.

4. QUELLEN: Beende mit "## Weiterfuehrende Literatur & Quellen" mit 3-5 echten, serioesen Ressourcen.

5. FAQ: Fuege "## Haeufig gestellte Fragen" mit 3 Fragen ein, jeweils mit ### formatiert.

LAENGE: 800-1.200 Woerter. Praegnant und uebersichtlich. Jeder Absatz muss seinen Platz verdienen.

FORMAT-REGELN:
- Gib NUR den Artikeltext in Markdown zurueck (kein Titel -- der kommt in die Front Matter)
- Beginne direkt mit einem ansprechenden Einleitungsabsatz
- Fuege den Titel NICHT als H1-Ueberschrift ein
- Verwende ## fuer Hauptabschnitte und ### fuer Unterabschnitte
- Fuege ein kurzes "Kernaussage" Blockzitat (>) nahe dem Anfang ein -- maximal ein bis zwei Saetze
- Verwende KEINE Emoji
- Kein Keyword-Stuffing
- Schreibe auf Deutsch
"""
    else:
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


def translate_article(english_text, topic):
    """Translate an English article to German using Claude."""
    client = get_anthropic_client()

    prompt = f"""Translate the following saxophone blog article from English to German.

IMPORTANT RULES:
- Keep the same Markdown formatting (##, ###, >, etc.)
- Keep all musician names, song titles, album titles, gear model names, and book titles in their original English/international form
- Translate section headings to German:
  - "From the Practice Room" -> "Aus dem Ueberaum"
  - "Common Mistakes to Avoid" -> "Haeufige Fehler vermeiden"
  - "Further Reading & Sources" -> "Weiterfuehrende Literatur & Quellen"
  - "Frequently Asked Questions" -> "Haeufig gestellte Fragen"
  - "Key Takeaway" -> "Kernaussage"
- Use informal "du" form (not "Sie")
- Keep the same warm, encouraging teacher tone
- Do NOT add or remove content, just translate
- Do NOT use emoji

Article to translate:

{english_text}"""

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


def build_front_matter(topic, image, lang="en", de_title=None, de_summary=None):
    """Build YAML front matter for an article."""
    now = datetime.now()
    title = de_title if (lang == "de" and de_title) else topic["title"]
    summary = de_summary if (lang == "de" and de_summary) else topic["summary"]
    category = SECTION_NAMES_DE.get(topic["section"], topic["section"]) if lang == "de" else topic["section"].replace("-", " ").title()

    fm_lines = ["---"]
    fm_lines.append(f'title: "{title}"')
    fm_lines.append(f'date: {now.strftime("%Y-%m-%dT%H:%M:%S+00:00")}')
    fm_lines.append(f'lastmod: {now.strftime("%Y-%m-%dT%H:%M:%S+00:00")}')
    fm_lines.append("draft: false")
    fm_lines.append(f'summary: "{summary}"')
    fm_lines.append("tags:")
    for tag in topic["tags"]:
        fm_lines.append(f'  - "{tag}"')
    fm_lines.append("categories:")
    fm_lines.append(f'  - "{category}"')
    if image:
        fm_lines.append('image: "featured.jpg"')
    fm_lines.append("authors:")
    fm_lines.append('  - "Sax & The City"')
    fm_lines.append("showTableOfContents: true")
    fm_lines.append("---")
    return "\n".join(fm_lines)


def create_hugo_page(topic, article_text_en, article_text_de, image):
    """Create a Hugo page bundle with English and German articles and featured image."""
    from PIL import Image

    section = topic["section"]
    slug = topic["slug"]
    bundle_dir = CONTENT_DIR / section / slug
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Save featured image (shared between languages)
    if image:
        image_path = bundle_dir / "featured.jpg"
        if image.width > 1600:
            ratio = 1600 / image.width
            new_size = (1600, int(image.height * ratio))
            image = image.resize(new_size, Image.LANCZOS)
        image.save(image_path, "JPEG", quality=85)
        print(f"  Image saved: {image_path}")

    has_image = image is not None or (bundle_dir / "featured.jpg").exists()

    # Generate German title and summary
    client = get_anthropic_client()
    meta_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": f'Translate this article title and summary to German. Return ONLY two lines: first line is the German title, second line is the German summary. No quotes, no labels, no extra text.\n\nTitle: {topic["title"]}\nSummary: {topic["summary"]}'}],
    )
    meta_lines = meta_response.content[0].text.strip().split("\n")
    de_title = meta_lines[0].strip() if len(meta_lines) > 0 else topic["title"]
    de_summary = meta_lines[1].strip() if len(meta_lines) > 1 else topic["summary"]

    # English version (index.md)
    fm_en = build_front_matter(topic, has_image, lang="en")
    en_path = bundle_dir / "index.md"
    with open(en_path, "w") as f:
        f.write(fm_en + "\n\n" + article_text_en + "\n")
    print(f"  English article saved: {en_path}")

    # German version (index.de.md)
    fm_de = build_front_matter(topic, has_image, lang="de", de_title=de_title, de_summary=de_summary)
    de_path = bundle_dir / "index.de.md"
    with open(de_path, "w") as f:
        f.write(fm_de + "\n\n" + article_text_de + "\n")
    print(f"  German article saved: {de_path}")

    return en_path


def main():
    """Generate the next article from the content plan."""
    # Check for specific topic slug or special commands
    target_slug = None
    count = 1
    translate_existing = False

    if len(sys.argv) > 1:
        if sys.argv[1] == "--translate-existing":
            translate_existing = True
        elif sys.argv[1].isdigit():
            count = int(sys.argv[1])
        else:
            target_slug = sys.argv[1]

    plan = load_plan()

    # Special mode: translate all existing English articles to German
    if translate_existing:
        translate_all_existing(plan)
        return

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

        # Generate English text
        print("  Writing English article with Claude...")
        article_text_en = generate_article_text(topic, lang="en")
        print(f"  English article generated ({len(article_text_en)} chars)")

        # Generate German text (translate from English for consistency)
        print("  Translating to German...")
        article_text_de = translate_article(article_text_en, topic)
        print(f"  German article generated ({len(article_text_de)} chars)")

        # Generate image
        print("  Generating featured image...")
        image = generate_featured_image(topic)

        # Create Hugo page bundle (both languages)
        create_hugo_page(topic, article_text_en, article_text_de, image)

        # Send email notification
        print("  Sending email notification...")
        send_notification_email(topic, article_text_en)

        # Mark as done
        topic["status"] = "done"
        save_plan(plan)
        print(f"  Done! Topic marked as completed.")

    print(f"\nFinished generating {count} article(s).")


def translate_all_existing(plan):
    """Translate all existing English articles that don't have a German version."""
    print("Translating existing articles to German...\n")
    translated = 0

    for topic in plan["topics"]:
        if topic["status"] != "done":
            continue

        section = topic["section"]
        slug = topic["slug"]
        bundle_dir = CONTENT_DIR / section / slug
        en_path = bundle_dir / "index.md"
        de_path = bundle_dir / "index.de.md"

        if not en_path.exists():
            continue
        if de_path.exists():
            print(f"  SKIP (already exists): {slug}")
            continue

        print(f"  Translating: {topic['title']}")

        # Read English article (skip front matter)
        with open(en_path) as f:
            content = f.read()
        parts = content.split("---", 2)
        if len(parts) >= 3:
            article_text_en = parts[2].strip()
        else:
            article_text_en = content

        # Translate
        article_text_de = translate_article(article_text_en, topic)

        # Get German title and summary
        client = get_anthropic_client()
        meta_response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{"role": "user", "content": f'Translate this article title and summary to German. Return ONLY two lines: first line is the German title, second line is the German summary. No quotes, no labels, no extra text.\n\nTitle: {topic["title"]}\nSummary: {topic["summary"]}'}],
        )
        meta_lines = meta_response.content[0].text.strip().split("\n")
        de_title = meta_lines[0].strip() if len(meta_lines) > 0 else topic["title"]
        de_summary = meta_lines[1].strip() if len(meta_lines) > 1 else topic["summary"]

        has_image = (bundle_dir / "featured.jpg").exists()
        fm_de = build_front_matter(topic, has_image, lang="de", de_title=de_title, de_summary=de_summary)

        with open(de_path, "w") as f:
            f.write(fm_de + "\n\n" + article_text_de + "\n")
        print(f"    Saved: {de_path}")
        translated += 1

    print(f"\nTranslated {translated} article(s) to German.")


if __name__ == "__main__":
    main()
