import hashlib
import os
import re
import subprocess
from urllib.parse import urlparse

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


def html_to_typst(element):
    if element.name is None:
        return escape_typst(element)

    content = ""
    for child in element.children:
        content += html_to_typst(child)

    if element.name in ["p", "div"]:
        # Avoid empty paragraphs
        if not content.strip() and not element.find("img"):
            return ""
        return f"{content}\n\n"
    elif element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        level = int(element.name[1])
        return f"{'=' * level} {content}\n\n"
    elif element.name == "strong" or element.name == "b":
        return f"*{content}*"
    elif element.name == "em" or element.name == "i":
        return f"_{content}_"
    elif element.name == "ul":
        # Process list items
        items = [child for child in element.children if child.name == "li"]
        result = ""
        for item in items:
            item_content = ""
            for child in item.children:
                item_content += html_to_typst(child)
            result += f"- {item_content.strip()}\n"
        return result + "\n"
    elif element.name == "ol":
        # Process list items
        items = [child for child in element.children if child.name == "li"]
        result = ""
        for item in items:
            item_content = ""
            for child in item.children:
                item_content += html_to_typst(child)
            result += f"+ {item_content.strip()}\n"
        return result + "\n"
    elif element.name == "blockquote":
        return f"#quote(block: true)[{content}]\n\n"
    elif element.name == "br":
        return "\n"
    elif element.name == "a":
        href = element.get("href", "")
        # Special case: Image wrapped in link
        if element.find("img"):
            return content  # Just return the content (the image) without the link wrapper for cleaner print

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
            local_path = download_image(src)
            if local_path:
                return f'#figure(image("{local_path}"), caption: [])\n\n'
        return ""

    return content


def scrape_substack(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    # Extract metadata detect
    # ... (existing metadata code) ...

    # Prepare footnotes extraction
    global FOOTNOTES
    FOOTNOTES = {}

    # Strategy: Find all elements that look like footnote definitions.
    # 1. Look for div.footnotes
    footnotes_div = soup.find("div", class_="footnotes")
    if footnotes_div:
        items = footnotes_div.find_all("li")
        for item in items:
            fid = item.get("id")
            if fid:
                # Remove backrefs
                for backref in item.find_all(class_="footnote-back"):
                    backref.decompose()
                FOOTNOTES[fid] = html_to_typst(item)
                FOOTNOTES["#" + fid] = FOOTNOTES[fid]  # link format
        footnotes_div.decompose()

    # 2. Look for any element with id ~ "footnote" that is NOT an anchor for a link (i.e. the definition)
    # Often substack uses <a id="footnote-1"></a> inside the text? No, usually it's at the bottom.
    # Let's find all text blocks that might be footnotes if valid div was not found or supplementary.
    # The grep showed "1 Schelling..." which looks like text.
    # Maybe the id is on the parent?

    # Let's clean up the soup before processing content
    # Extract content div
    content_div = soup.find("div", class_="body markup")
    if not content_div:
        content_div = soup.find("div", class_="available-content")

    typst_content = ""
    if content_div:
        # Pass 1: Scan content_div for footnote definitions (targets)
        # We look for links or spans with ids that look like footnotes
        # In Substack, the reference is <a href="#footnote-1">1</a>
        # The content is usually <p id="footnote-1">...</p> or similar?
        # Or <a id="footnote-1"></a>1 ...

        # Let's assume standard behavior first. If the previous grep showed [1]Schelling,
        # it implies the link text "1" was rendered, and "Schelling" followed.
        # This occurs if the footnote definition is just appended text.

        # New approach: Find all elements with id starting with "footnote-"
        # that are likely definitions.
        # Avoid removing the *references* which might also have ids? Usually references have class "footnote-anchor"

        definitions = content_div.find_all(attrs={"id": re.compile(r"footnote-.*")})
        for defi in definitions:
            # Check if this is a definition
            # A definition usually contains the text.
            # A reference usually contains just a number "1", "2" etc.

            # If it's a link with href, it's a reference (or back reference).
            if defi.name == "a" and defi.get("href"):
                continue

            # If it text content is long, likely a definition
            text_len = len(defi.get_text(strip=True))
            if text_len > 5:
                fid = defi.get("id")
                # Clean checks
                # Remove label if present (e.g. "1")
                # But html_to_typst handles content.

                # capture content
                content_str = html_to_typst(defi)
                # If content starts with "1" or "[1]", strip it
                content_str = re.sub(r"^\[?\d+\]?\s*", "", content_str)

                FOOTNOTES[fid] = content_str
                FOOTNOTES["#" + fid] = content_str

                # Remove from DOM so it doesn't appear in body
                defi.decompose()

        # Pass 2: Rendering
        typst_content = html_to_typst(content_div)

    # Extract metadata detect
    title = "Untitled"

    # Try meta tag first
    meta_title = soup.find("meta", property="og:title")
    if meta_title:
        title = meta_title.get("content")
    else:
        title_elem = soup.find("h1", class_="post-title")
        if not title_elem:
            title_elem = soup.find("h1")  # Fallback to first h1
        if title_elem:
            title = title_elem.get_text(strip=True)

    author = "Unknown Author"
    # Try meta tag for author
    # <meta name="author" content="Slavoj Žižek">
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author:
        author = meta_author.get("content")
    else:
        author_elem = soup.find(
            "a", class_="pencraft pc-display-flex pc-gap-4 pc-reset"
        )
        # Fallback author search
        if not author_elem:
            author_elem = soup.find(
                "div",
                class_="pencraft pc-display-flex pc-flex-direction-column pc-gap-4 pc-reset",
            )
        if author_elem:
            author = author_elem.get_text(strip=True)

    date = ""
    date_elem = soup.find("div", class_="post-date")
    if not date_elem:
        date_elem = soup.find("time")
    date = date_elem.get_text(strip=True) if date_elem else ""

    return {"title": title, "author": author, "date": date, "content": typst_content}


def generate_typst_file(data, output_file="article.typ"):
    title = "Untitled"

    # Try meta tag first
    meta_title = soup.find("meta", property="og:title")
    if meta_title:
        title = meta_title.get("content")
    else:
        title_elem = soup.find("h1", class_="post-title")
        if not title_elem:
            title_elem = soup.find("h1")  # Fallback to first h1
        if title_elem:
            title = title_elem.get_text(strip=True)

    author = "Unknown Author"
    # Try meta tag for author
    # <meta name="author" content="Slavoj Žižek">
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author:
        author = meta_author.get("content")
    else:
        author_elem = soup.find(
            "a", class_="pencraft pc-display-flex pc-gap-4 pc-reset"
        )
        # Fallback author search
        if not author_elem:
            author_elem = soup.find(
                "div",
                class_="pencraft pc-display-flex pc-flex-direction-column pc-gap-4 pc-reset",
            )
        if author_elem:
            author = author_elem.get_text(strip=True)

    date = ""
    date_elem = soup.find("div", class_="post-date")
    if not date_elem:
        date_elem = soup.find("time")
    date = date_elem.get_text(strip=True) if date_elem else ""

    # Extract content
    content_div = soup.find("div", class_="body markup")
    if not content_div:
        content_div = soup.find("div", class_="available-content")

    typst_content = ""
    if content_div:
        typst_content = html_to_typst(content_div)

    return {"title": title, "author": author, "date": date, "content": typst_content}


def generate_typst_file(data, output_file="article.typ"):
    template = f"""
#import "template.typ": article

#show: doc => article(
  title: "{escape_typst(data["title"])}",
  author: "{escape_typst(data["author"])}",
  date: "{escape_typst(data["date"])}",
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
    url = "https://slavoj.substack.com/p/what-can-psychoanalysis-tell-us-about-062"
    print(f"Scraping {url}...")
    data = scrape_substack(url)
    print(f"Fetched: {data['title']}")

    generate_typst_file(data)
    compile_typst("article.typ")
