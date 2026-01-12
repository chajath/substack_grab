import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

FOOTNOTES = {}


def clean_text(text):
    return text.strip()


def escape_typst(text):
    # Escape characters special in Typst
    chars = ["*", "_", "`", "$", "#", "[", "]", "<", ">", "@"]
    for char in chars:
        text = text.replace(char, "\\" + char)
    return text


def format_date(date_string):
    if not date_string:
        return ""

    date_string = date_string.strip()
    dt = None

    # Try ISO format first (handles TZ, various separators)
    try:
        dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
    except ValueError:
        pass

    if not dt and "T" in date_string:
        try:
            dt = datetime.fromisoformat(date_string.split("T")[0])
        except ValueError:
            pass

    formats = [
        "%b %d, %Y",  # Nov 26, 2025
        "%B %d, %Y",  # November 26, 2025
        "%d %b %Y",  # 26 Nov 2025
        "%Y-%m-%d",  # 2025-11-26
    ]

    if not dt:
        for fmt in formats:
            try:
                dt = datetime.strptime(date_string, fmt)
                break
            except ValueError:
                continue

    if dt:
        # User requested: mmm dd yyyy (e.g. Jan 11 2026) or standard Mmm dd, YYYY?
        # Standard prose is "Jan 11, 2026".
        return dt.strftime("%b %d, %Y")

    return date_string


def download_image(url, folder="images"):
    if not os.path.exists(folder):
        os.makedirs(folder)

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        # Create a safe filename from the URL
        parsed = urlparse(url)
        path = parsed.path

        # Look for format in content-type
        ct = response.headers.get("content-type", "").lower()
        ext = ""
        if "image/jpeg" in ct or "image/jpg" in ct:
            ext = ".jpg"
        elif "image/png" in ct:
            ext = ".png"
        elif "image/gif" in ct:
            ext = ".gif"
        elif "image/webp" in ct:
            ext = ".webp"
        elif "image/svg+xml" in ct:
            ext = ".svg"

        if not ext:
            # Fallback to extension in URL
            ext = os.path.splitext(path)[1]

        if not ext:
            ext = ".jpg"  # Final fallback

        # Use simple hash for filename to avoid issues
        filename = hashlib.md5(url.encode()).hexdigest() + ext
        filepath = os.path.join(folder, filename)

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)

        return filepath
    except Exception as e:
        print(f"Failed to download image: {url}, error: {e}")
        return None


def html_to_typst(element, base_url=""):
    if element.name is None:
        return escape_typst(element)

    if element.name in ["script", "style", "noscript"]:
        return ""
    
    # Exclude print-specific navigation and headers
    if element.name in ["div", "section"] and any(cls in element.get("class", []) for cls in [
        "print-nav", 
        "series-nav", 
        "post__title__wrapper",  # Contains Duplicate Title, Author, Date, Tags
        "post__sidebar",         # Contains Author Profile, Share Buttons
        "footer__wrapper",       # Contains Footer/Newsletter
        "d-print-none",          # Generic print hider
    ]):
        return ""
    
    if element.name == "aside": # Remove all sidebars (Author profile, etc)
         return ""

    if element.name == "header":
        return ""

    if element.name == "div" and "datawrapper-wrap" in element.get("class", []):
        if element.has_attr("data-attrs"):
            try:
                attrs = json.loads(element["data-attrs"])
                img_url = attrs.get("thumbnail_url") or attrs.get("thumbnail_url_full")
                if img_url:
                    if base_url:
                        img_url = urljoin(base_url, img_url)
                    local_path = download_image(img_url)
                    title = attrs.get("title", "")
                    desc = attrs.get("description", "")

                    caption_parts = []
                    if title:
                        caption_parts.append(f"*{escape_typst(title)}*")
                    if desc:
                        caption_parts.append(escape_typst(desc))

                    caption_content = " ".join(caption_parts)

                    if local_path:
                        return f'#figure(image("{local_path}", width: 100%), caption: [{caption_content}])\n\n'
            except Exception as e:
                print(f"Error parsing datawrapper: {e}")

    content = ""
    for child in element.children:
        content += html_to_typst(child, base_url)

    if element.name in ["p", "div"]:
        # Avoid empty paragraphs
        if not content.strip() and not element.find("img"):
            return ""
        return f"{content}\n\n"
    elif element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        level = int(element.name[1])
        return f"{'=' * level} {content}\n\n"
    elif element.name == "strong" or element.name == "b":
        if not content.strip():
            return ""
        return f"#strong[{content}]"
    elif element.name == "em" or element.name == "i":
        if not content.strip():
            return ""
        return f"#emph[{content}]"
    elif element.name == "ul":
        # Process list items
        items = [child for child in element.children if child.name == "li"]
        result = ""
        for item in items:
            item_content = ""
            for child in item.children:
                item_content += html_to_typst(child, base_url)
            result += f"- {item_content.strip()}\n"
        return result + "\n"
    elif element.name == "ol":
        # Process list items
        items = [child for child in element.children if child.name == "li"]
        result = ""
        for item in items:
            item_content = ""
            for child in item.children:
                item_content += html_to_typst(child, base_url)
            result += f"+ {item_content.strip()}\n"
        return result + "\n"
    elif element.name == "blockquote":
        return f"#quote(block: true)[{content}]\n\n"
    elif element.name == "br":
        return "\n"
    elif element.name == "a":
        href = element.get("href", "")
        # Resolve relative URLs
        if href and base_url:
            href = urljoin(base_url, href)

        # Special case: Image wrapped in link
        if element.find("img"):
            return content  # Just return the content (the image) without the link wrapper for cleaner print

        # Check if content is just an image filename (common artifact in converted footnotes/captions)
        text_content = element.get_text().strip().lower()
        if (
            text_content.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
            and len(text_content) < 50
        ):
            return ""

        # Check for absolute URLs that point to fragments
        parsed_href = urlparse(href)
        # If fragment exists and looks like a footnote
        if parsed_href.fragment and (
            parsed_href.fragment.startswith("footnote")
            or "footnote" in parsed_href.fragment
        ):
            fragment = "#" + parsed_href.fragment
            # Try to resolve content
            fn_content = FOOTNOTES.get(fragment)
            if not fn_content:
                # Try partial match (sometimes ids vary slightly)
                # or just the id without #
                fn_content = FOOTNOTES.get(parsed_href.fragment)

            if fn_content:
                return f"#footnote[{fn_content.strip()}]"

            # If we think it IS a footnote but we missed the content (maybe dynamic?),
            # Try to just print text.
            # But safer is to return the link if content missing?
            # Or assume the content is elsewhere?

            # Use text as number if it is a number
            text_content = element.get_text().strip()
            if text_content.isdigit() or (
                text_content.startswith("[") and text_content.endswith("]")
            ):
                # It's a reference number
                # If we don't have content, maybe we shouldn't make it a footnote?
                # formatting it as SUPER avoids the big blue link.
                return f"#super[{text_content}]"

        return f'#link("{href}")[{content}]'
    elif element.name == "img":
        src = element.get("src")
        if src:
            if base_url:
                src = urljoin(base_url, src)
            local_path = download_image(src)
            if local_path:
                return f'#figure(image("{local_path}"), caption: [])\n\n'
        return ""

    return content


def scrape_url(url):
    # Special handling for Quanta Magazine - force print mode
    if "quantamagazine.org" in url and "print=1" not in url:
        if "?" in url:
            url += "&print=1"
        else:
            url += "?print=1"
        print(f"Switching to print mode: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Check for Substack session cookie in environment variables
    # You can set this by running: export SUBSTACK_COOKIE="...your_cookie_value..."
    cookie_value = os.environ.get("SUBSTACK_COOKIE")
    cookies = {}
    if cookie_value:
        cookies["substack.sid"] = cookie_value
        print("Using provided SUBSTACK_COOKIE for authentication.")

    response = requests.get(url, headers=headers, cookies=cookies)
    soup = BeautifulSoup(response.content, "html.parser")

    # Metadata extraction (Title, Author, Date) - moved early to be generic
    title = "Untitled"
    meta_title = soup.find("meta", property="og:title")
    if meta_title:
        title = meta_title.get("content")
    else:
        title_elem = soup.find("h1", class_="post-title")
        if not title_elem:
            title_elem = soup.find("h1")  # Generic fallback
        if title_elem:
            title = title_elem.get_text(strip=True)

    author = "Unknown Author"
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author:
        author = meta_author.get("content")
    else:
        # Try generic bylines
        author_elem = soup.find(class_=re.compile("author|byline", re.I))
        if author_elem:
            author = author_elem.get_text(strip=True)

    date = ""
    meta_date = soup.find("meta", property="article:published_time")
    if meta_date:
        date = meta_date.get("content")
    if not date:
        date_elem = soup.find("time")  # Generic time tag
        if date_elem:
            # Prefer datetime attribute
            if date_elem.get("datetime"):
                date = date_elem.get("datetime")
            else:
                date = date_elem.get_text(strip=True)

    # Try JSON-LD if logic above failed
    if not date:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                # Check for datePublished in top level
                if "datePublished" in data:
                    date = data["datePublished"]
                    break
                # Check graph if available
                if "@graph" in data:
                    for item in data["@graph"]:
                        if "datePublished" in item:
                            date = item["datePublished"]
                            break
                    if date:
                        break
            except:
                pass

    # Normalize date format
    date = format_date(date)

    # Content Extraction Strategy

    # 1. Try Substack specific containers
    content_div = soup.find("div", class_="body markup")
    if not content_div:
        content_div = soup.find("div", class_="available-content")

    # 2. Try Generic semantic tags
    if not content_div:
        content_div = soup.find("article")

    if not content_div:
        content_div = soup.find("main")

    # 3. Try Generic class names
    if not content_div:
        # find div with class containing 'content', 'post', 'entry', 'article'
        # This is heuristic and might be too broad, so we prioritize 'article' and 'post-content'
        possible_classes = [
            "post-content",
            "entry-content",
            "article-content",
            "content",
        ]
        for cls in possible_classes:
            content_div = soup.find("div", class_=cls)
            if content_div:
                break

    # 4. Fallback: just separate body? No, that's too dangerous.

    if not content_div:
        print("Warning: Could not identify main content area. Output might be empty.")
        # Create a dummy div to return empty processing
        content_div = soup.new_tag("div")

    # Prepare footnotes extraction
    global FOOTNOTES
    FOOTNOTES = {}

    # Strategy: Find all elements that look like footnote definitions.
    # 1. Look for div.footnotes (Generic & Substack)
    footnotes_div = soup.find(
        "div", class_="footnotes"
    )  # Standard class often used by markdown parsers
    if footnotes_div:
        # Check for ordered list or list items
        items = footnotes_div.find_all("li")
        for item in items:
            fid = item.get("id")
            if fid:
                # Generic backref removal
                # Remove by class
                for backref in item.find_all(
                    class_=re.compile(r"backref|footnote-back", re.I)
                ):
                    backref.decompose()
                # Remove by text symbol (↩, ↑) often used as backref
                for link in item.find_all("a"):
                    if link.get_text(strip=True) in ["↩", "↑", "^", "return"]:
                        link.decompose()

                FOOTNOTES[fid] = html_to_typst(item)
                FOOTNOTES["#" + fid] = FOOTNOTES[fid]  # link format
        footnotes_div.decompose()

    # 2. Look for substack specific footnote definitions (id="footnote-...")
    definitions = content_div.find_all(attrs={"id": re.compile(r"footnote-.*")})
    for defi in definitions:
        if defi.name == "a" and defi.get("href"):
            continue  # Skip links

        text_len = len(defi.get_text(strip=True))
        if text_len > 5:
            fid = defi.get("id")
            content_str = html_to_typst(defi)
            content_str = re.sub(r"^\[?\d+\]?\s*", "", content_str)
            FOOTNOTES[fid] = content_str
            FOOTNOTES["#" + fid] = content_str
            defi.decompose()

    # Cleanup unwanted elements - Generic & Substack
    unwanted_classes = [
        # Substack
        "share-dialog-title",
        "share-button",
        "subscription-widget-wrap",
        "subscribe-widget",
        "post-footer",
        "comments-section",
        "buttons",
        "utility-bar",
        "paywall-cta",
        "share-post",
        "post-footer-cta",
        # Generic
        "sidebar",
        "nav",
        "navigation",
        "footer",
        "menu",
        "ad",
        "advertisement",
        "popup",
        "newsletter-signup",
    ]

    # Remove unwanted classes
    if content_div:
        for element in content_div.find_all():
            # Check if element has attributes (skip strings, comments, etc.)
            if getattr(element, "attrs", None) is None:
                continue

            # element.get('class') returns a list of strings or None
            classes = element.get("class")
            if not classes:
                continue

            if any(cls in unwanted_classes for cls in classes):
                element.decompose()
            # Also partial match checks for 'share', 'subscribe'
            elif any(
                "share" in cls.lower() or "subscribe" in cls.lower() for cls in classes
            ):
                # Be careful not to delete content paragraphs that might have these words in class names arbitrarily?
                # Safe for widgets Usually.
                if element.name in ["div", "aside", "section"]:
                    element.decompose()

    # Remove specific text buttons/links often found in body - Generic approach
    if content_div:
        for elem in content_div.find_all(["button", "a", "div", "p"]):
            # Simplified logic: if short text and contains keywords
            text = elem.get_text(strip=True).lower()
            keywords = ["subscribe", "share", "leave a comment", "donate", "sign up"]

            # Exact match or short phrases
            if any(text == k for k in keywords) or (
                len(text) < 50 and any(k in text for k in keywords)
            ):
                if elem.name in ["button", "a"]:
                    elem.decompose()
                # If div/p is mostly empty/just this text
                elif elem.name in ["div", "p"] and len(elem.find_all()) <= 1:
                    elem.decompose()

    # Pass 2: Rendering
    typst_content = html_to_typst(content_div) if content_div else ""

    return {
        "title": title,
        "author": author,
        "date": date,
        "content": typst_content,
        "url": url,
    }


# Keeping scrape_substack as alias for backward compatibility if needed,
# but main calls scrape_url
def scrape_substack(url):
    return scrape_url(url)


def generate_typst_file(data, output_file="article.typ"):
    template = f"""
#import "template.typ": article

#show: doc => article(
  title: "{escape_typst(data["title"])}",
  author: "{escape_typst(data["author"])}",
  date: "{escape_typst(data["date"])}",
  url: "{escape_typst(data["url"])}",
  [
{data["content"]}
  ]
)
"""
    with open(output_file, "w") as f:
        f.write(template)
    print(f"Generated {output_file}")


def compile_typst(filename):
    try:
        subprocess.run(["typst", "compile", filename], check=True)
        print(f"Compiled {filename} to PDF.")
    except FileNotFoundError:
        print("Error: 'typst' command not found. Please install Typst.")
    except subprocess.CalledProcessError as e:
        print(f"Error compiling Typst file: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python grab_substack.py <substack_url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Scraping {url}...")
    data = scrape_substack(url)
    print(f"Fetched: {data['title']}")

    # Create safe filename from title
    safe_title = re.sub(r"[^\w\s-]", "", data["title"]).strip().lower()
    safe_title = re.sub(r"[-\s]+", "-", safe_title)
    if not safe_title:
        safe_title = "article"

    output_filename = f"{safe_title}.typ"

    generate_typst_file(data, output_file=output_filename)
    compile_typst(output_filename)
