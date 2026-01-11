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

Run the script to fetch the predefined URL and generate the PDF:

```bash
python grab_substack.py
```

The output PDF will be generated as `article.pdf`.

## Customization

You can modify `grab_substack.py` to change the target URL or `template.typ` to adjust the visual style.
