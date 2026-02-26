#!/usr/bin/env python3
"""
Sax & The City -- AI Article Generator
Generates SEO-optimized saxophone articles with AI-generated images.
Uses Claude Sonnet for text and Imagen for featured images.
"""

import json
import os
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CONTENT_DIR = PROJECT_DIR / "content"
PLAN_FILE = SCRIPT_DIR / "content_plan.json"


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


def generate_article_text(topic):
    """Generate article text using Claude Sonnet."""
    import anthropic

    api_key = os.environ.get("CLAUDE_API_KEY_1") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No Anthropic API key found")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Write a comprehensive, SEO-optimized blog article for "Sax & The City", a saxophone blog for beginners and intermediate players.

ARTICLE DETAILS:
- Title: {topic['title']}
- Category: {topic['section'].replace('-', ' ').title()}
- Summary: {topic['summary']}
- Target tags: {', '.join(topic['tags'])}

WRITING GUIDELINES:
- Length: 1,500-2,500 words
- Tone: Friendly, encouraging, like a supportive teacher. Warm and motivating. "You can do this!"
- Audience: Beginners and intermediate saxophone players across all styles (jazz, pop, funk, classical, R&B)
- Reference real musicians, real gear, real songs where relevant
- Use clear headings (H2 and H3) to structure the content
- Include practical, actionable advice
- End with a FAQ section (3-5 questions) using this exact format:

## Frequently Asked Questions

### Question here?

Answer here.

IMPORTANT FORMAT RULES:
- Return ONLY the article body in Markdown (no title -- that goes in front matter)
- Start directly with an engaging introduction paragraph
- Do NOT include the title as an H1 heading
- Use ## for main sections and ### for subsections
- Include a "Key Takeaways" or "Quick Summary" box near the top using a blockquote (>)
- Do NOT use emoji
- Write naturally, avoid keyword stuffing
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

        # Mark as done
        topic["status"] = "done"
        save_plan(plan)
        print(f"  Done! Topic marked as completed.")

    print(f"\nFinished generating {count} article(s).")


if __name__ == "__main__":
    main()
