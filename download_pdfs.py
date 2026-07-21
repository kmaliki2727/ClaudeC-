#!/usr/bin/env python3
"""
download_pdfs.py
----------------
Downloads the reports listed in Research_mapping.xlsx and names each file by its
index number, e.g. Index_1.pdf, Index_2.pdf, ...

WHY THIS ISN'T A ONE-LINER:
  Only ~24 of the 194 links point straight at a .pdf file. The other ~170 are
  landing / publication pages (e.g. iea.org/reports/world-energy-outlook-2025).
  For those, this script fetches the page and tries to find the real PDF link
  inside it. When it genuinely can't (gated downloads, JS-rendered pages,
  registration walls), it records the row as "MANUAL" in a report CSV so you
  can grab those few by hand instead of ending up with 170 junk HTML files.

USAGE:
  1. Put this script in the same folder as Research mapping.xlsx
  2. pip install requests pandas openpyxl beautifulsoup4
  3. python download_pdfs.py

OUTPUT:
  ./downloaded_pdfs/Index_<N>.pdf      -- the PDFs
  ./download_report.csv                -- per-row status (OK / MANUAL / FAILED)

Re-running is safe: files already downloaded are skipped, so you can run it
again to retry only the ones that failed.
"""

import os
import re
import time
import urllib.parse as urlparse

import pandas as pd
import requests

try:
    from bs4 import BeautifulSoup
    HAVE_BS4 = True
except ImportError:
    HAVE_BS4 = False  # falls back to regex link-finding

# ---------------------------------------------------------------- config
EXCEL_FILE   = "Research mapping.xlsx"
SHEET_NAME   = "Research institutions mapped to"
LINK_COL     = "Link"
INDEX_COL    = "Number"
OUT_DIR      = "downloaded_pdfs"
REPORT_CSV   = "download_report.csv"
TIMEOUT      = 30          # seconds per request
PAUSE        = 1.0         # polite delay between rows (seconds)
MAX_HTML_MB  = 15          # don't scan HTML pages larger than this

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/pdf,application/xhtml+xml,*/*",
}


# ---------------------------------------------------------------- helpers
def looks_like_pdf(content: bytes) -> bool:
    """A real PDF starts with the %PDF magic bytes."""
    return content[:5] == b"%PDF-"


def find_pdf_in_html(html: str, base_url: str):
    """Return the most plausible absolute PDF URL found in an HTML page, or None."""
    candidates = []

    if HAVE_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            candidates.append(a["href"])
        # Some sites expose the PDF via <meta> or data-attributes
        for tag in soup.find_all(attrs={"data-download-url": True}):
            candidates.append(tag["data-download-url"])
    else:
        candidates = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)

    # Score candidates: prefer links ending in .pdf, then ones containing 'pdf'
    scored = []
    for href in candidates:
        low = href.lower()
        if low.endswith(".pdf"):
            scored.append((2, href))
        elif ".pdf" in low or "/pdf" in low or "download" in low and "pdf" in low:
            scored.append((1, href))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    return urlparse.urljoin(base_url, best)


def save_pdf(content: bytes, index: int) -> str:
    path = os.path.join(OUT_DIR, f"Index_{index}.pdf")
    with open(path, "wb") as f:
        f.write(content)
    return path


def fetch(url: str, session: requests.Session):
    """GET a url, following redirects. Returns the response or raises."""
    return session.get(url, headers=HEADERS, timeout=TIMEOUT,
                       allow_redirects=True, stream=True)


# ---------------------------------------------------------------- main
def process_row(index: int, url: str, session: requests.Session):
    """Returns (status, saved_path_or_empty, note)."""
    out_path = os.path.join(OUT_DIR, f"Index_{index}.pdf")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
        return ("OK", out_path, "already downloaded (skipped)")

    if not isinstance(url, str) or not url.lower().startswith("http"):
        return ("FAILED", "", f"not a valid URL: {url!r}")

    try:
        resp = fetch(url, session)
    except Exception as e:
        return ("FAILED", "", f"request error: {type(e).__name__}: {e}")

    if resp.status_code != 200:
        return ("FAILED", "", f"HTTP {resp.status_code}")

    ctype = resp.headers.get("Content-Type", "").lower()

    # Case A: the response is itself a PDF (covers direct .pdf links AND
    # landing pages that redirect straight to a PDF).
    if "application/pdf" in ctype or url.lower().endswith(".pdf"):
        content = resp.content
        if looks_like_pdf(content):
            return ("OK", save_pdf(content, index), "direct PDF")
        # content-type lied; fall through to HTML handling
    # Case B: it's an HTML page -- look inside for a PDF link.
    content = resp.content
    if looks_like_pdf(content):                      # some servers omit ctype
        return ("OK", save_pdf(content, index), "direct PDF (by magic bytes)")

    if len(content) > MAX_HTML_MB * 1024 * 1024:
        return ("MANUAL", "", "page too large to scan for a PDF link")

    try:
        html = content.decode("utf-8", errors="ignore")
    except Exception:
        return ("MANUAL", "", "could not decode page")

    pdf_url = find_pdf_in_html(html, resp.url)
    if not pdf_url:
        return ("MANUAL", "", "no PDF link found on landing page (grab by hand)")

    try:
        r2 = fetch(pdf_url, session)
        if r2.status_code == 200 and looks_like_pdf(r2.content):
            return ("OK", save_pdf(r2.content, index), f"found PDF at {pdf_url}")
        return ("MANUAL", "", f"candidate link was not a PDF: {pdf_url}")
    except Exception as e:
        return ("MANUAL", "", f"error fetching found PDF link: {e}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
    df = df[[INDEX_COL, LINK_COL]].dropna(subset=[INDEX_COL, LINK_COL])

    session = requests.Session()
    rows = []
    total = len(df)
    for i, (_, row) in enumerate(df.iterrows(), 1):
        index = int(row[INDEX_COL])
        url = str(row[LINK_COL]).strip()
        status, path, note = process_row(index, url, session)
        rows.append({"Index": index, "Link": url, "Status": status,
                     "SavedFile": path, "Note": note})
        print(f"[{i:>3}/{total}] Index_{index:<4} {status:<7} {note}")
        time.sleep(PAUSE)

    report = pd.DataFrame(rows).sort_values("Index")
    report.to_csv(REPORT_CSV, index=False)

    ok = (report["Status"] == "OK").sum()
    manual = (report["Status"] == "MANUAL").sum()
    failed = (report["Status"] == "FAILED").sum()
    print("\n" + "=" * 55)
    print(f"Done. {ok} downloaded, {manual} need manual grab, {failed} failed.")
    print(f"PDFs  -> ./{OUT_DIR}/")
    print(f"Report-> ./{REPORT_CSV}  (open it to see MANUAL/FAILED rows)")
    print("Re-run the script to retry the ones that didn't succeed.")


if __name__ == "__main__":
    main()
