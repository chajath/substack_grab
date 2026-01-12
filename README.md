# Substack to Typst PDF

This tool scrapes a Substack post and converts it into a clean, two-column PDF using Typst.

## Prerequisites

- [Python 3](https://www.python.org/)
- [Typst](https://typst.app/) (CLI tool)

## Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure `typst` is in your system PATH.

## Usage

Run the script with the URL of the post you want to grab:

```bash
python grab_substack.py "https://slavoj.substack.com/p/what-can-psychoanalysis-tell-us-about-062"
```

The output PDF will be generated as `article.pdf`.

## Customization

You can modify `grab_substack.py` to change the target URL or `template.typ` to adjust the visual style.

## Paid Posts

To scrape paid posts that you have access to:

1.  Log in to Substack in your browser.
2.  Open Developer Tools (F12) -> Application/Storage -> Cookies.
3.  Find the cookie named `substack.sid`.
4.  Copy its value.
5.  Set it as an environment variable when running the script:

```bash
export SUBSTACK_COOKIE="your_cookie_value_here"
python grab_substack.py "https://example.substack.com/p/paid-post-slug"
```
