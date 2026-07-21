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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from bs4 import BeautifulSoup
    HAVE_BS4 = True
except ImportError:
    HAVE_BS4 = False  # falls back to regex link-finding

# ---------------------------------------------------------------- config
EXCEL_FILE      = "Research mapping.xlsx"
SHEET_NAME      = "Research institutions mapped to"
LINK_COL        = "Link"
INDEX_COL       = "Number"
OUT_DIR         = "downloaded_pdfs"
REPORT_CSV      = "download_report.csv"
TIMEOUT         = 30          # seconds per request
PAUSE           = 1.0         # polite delay between rows (seconds)
MAX_HTML_MB     = 15          # don't scan HTML pages larger than this
MAX_CANDIDATES  = 4           # how many candidate PDF links to try per landing page
MAX_RETRIES     = 3           # retries for transient network/HTTP errors

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/pdf,application/xhtml+xml,*/*",
}


def build_session() -> requests.Session:
    """Session with retries on transient network/HTTP errors (timeouts, 429, 5xx)."""
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------- helpers
def looks_like_pdf(content: bytes) -> bool:
    """A real PDF starts with the %PDF magic bytes."""
    return content[:5] == b"%PDF-"


def find_meta_refresh(html: str, base_url: str):
    """Some publishers bounce through <meta http-equiv="refresh" content="0;url=...">."""
    m = re.search(
        r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*url=([^"\';]+)',
        html, flags=re.I,
    )
    if m:
        return urlparse.urljoin(base_url, m.group(1).strip())
    return None


DOWNLOAD_WORDS = ("download", "full report", "read the report", "get the report", "pdf")


def find_pdf_candidates(html: str, base_url: str):
    """Return a ranked list of plausible absolute PDF URLs found in an HTML page."""
    scored = []

    if HAVE_BS4:
        soup = BeautifulSoup(html, "html.parser")

        # citation_pdf_url is the standard meta tag academic/institutional
        # publishing platforms use to point directly at the PDF -- treat it
        # as the strongest possible signal.
        for meta in soup.find_all("meta", attrs={"name": re.compile("citation_pdf_url", re.I)}):
            content = meta.get("content")
            if content:
                scored.append((4, content))

        for tag in soup.find_all(attrs={"data-download-url": True}):
            scored.append((3, tag["data-download-url"]))

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True).lower()
            low = href.lower()
            if low.endswith(".pdf"):
                scored.append((3, href))
            elif ".pdf" in low or "/pdf" in low:
                scored.append((2, href))
            elif any(word in text for word in DOWNLOAD_WORDS):
                # href doesn't look like a PDF, but the link text does
                # (common for buttons like "Download full report").
                scored.append((1, href))
    else:
        for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I):
            low = href.lower()
            if low.endswith(".pdf"):
                scored.append((3, href))
            elif ".pdf" in low or "/pdf" in low:
                scored.append((2, href))

    if not scored:
        return []

    seen = set()
    ranked = []
    for score, href in sorted(scored, key=lambda x: x[0], reverse=True):
        abs_url = urlparse.urljoin(base_url, href)
        if abs_url not in seen and abs_url.lower().startswith("http"):
            seen.add(abs_url)
            ranked.append(abs_url)

    return ranked[:MAX_CANDIDATES]


def save_pdf(content: bytes, index: int) -> str:
    path = os.path.join(OUT_DIR, f"Index_{index}.pdf")
    with open(path, "wb") as f:
        f.write(content)
    return path


def fetch(url: str, session: requests.Session, referer: str = None):
    """GET a url, following redirects. Returns the response or raises.

    Some servers reject direct/hotlinked PDF requests unless the Referer
    looks like it came from their own site, so callers fetching a link
    found *inside* a page should pass that page's URL as referer.
    """
    headers = HEADERS if not referer else {**HEADERS, "Referer": referer}
    return session.get(url, headers=headers, timeout=TIMEOUT,
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

    # Some publishers bounce the landing page through a meta-refresh before
    # the real content loads -- follow one hop of that before scanning.
    refresh_url = find_meta_refresh(html, resp.url)
    if refresh_url:
        try:
            resp2 = fetch(refresh_url, session, referer=resp.url)
            if looks_like_pdf(resp2.content):
                return ("OK", save_pdf(resp2.content, index), "direct PDF (via meta-refresh)")
            html = resp2.content.decode("utf-8", errors="ignore")
            resp = resp2
        except Exception:
            pass  # fall through and try scanning the original page anyway

    candidates = find_pdf_candidates(html, resp.url)
    if not candidates:
        return ("MANUAL", "", "no PDF link found on landing page (grab by hand)")

    errors = []
    for pdf_url in candidates:
        try:
            r2 = fetch(pdf_url, session, referer=resp.url)
            if r2.status_code == 200 and looks_like_pdf(r2.content):
                return ("OK", save_pdf(r2.content, index), f"found PDF at {pdf_url}")
            errors.append(f"{pdf_url} -> HTTP {r2.status_code}, not a PDF")
        except Exception as e:
            errors.append(f"{pdf_url} -> {type(e).__name__}: {e}")

    return ("MANUAL", "", f"tried {len(candidates)} candidate link(s), none were a PDF: "
                           + "; ".join(errors))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
    df = df[[INDEX_COL, LINK_COL]].dropna(subset=[INDEX_COL, LINK_COL])

    session = build_session()
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
