#!/usr/bin/env python3
"""
Part 3 data source: PressPlay premarket article's stock-group lists,
cross-referenced against chengwaye.com/daily's AI group classification.

Article source (paid membership content):
    https://www.pressplay.cc/member/learning/projects/1002F3D338218A43A3A65E8D2A80376F/articles
Cross-reference source (free, public, no login):
    https://chengwaye.com/daily

WHY THIS NEEDS LOGIN, AND WHO HANDLES THE PASSWORD (read this first):
Unlike Part 1/2's sources, the PressPlay article lives behind a paid
membership login. This script logs in using PRESSPLAY_EMAIL /
PRESSPLAY_PASSWORD read from the environment -- populated from GitHub
Actions secrets (see the collect step in build-premarket-page.yml). You
set the actual values yourself, directly in GitHub's own Settings ->
Secrets and variables -> Actions UI. This script (and whoever maintains
it) only ever reads them from the environment at run time; they are never
logged, printed, or committed anywhere in this repo.

KNOWN RISK (explained to and knowingly accepted by the repo owner,
2026-08-20 -- not a surprise discovered after the fact): PressPlay's own
terms of service may not permit automated login to a paid membership
account, and repeated automated logins from GitHub Actions' shared
datacenter IPs could get flagged or blocked -- the same class of problem
that Part 1 first hit with wantgoo.com's Cloudflare protection (see
tx_night_session.py's module docstring for that whole investigation). If
this script starts failing consistently where it used to work, that risk
materializing is the first thing to check, not a code regression.

FETCH METHOD -- headless browser (Playwright) for the article, requests
for chengwaye.com:
The PressPlay side needs a real browser because it needs to authenticate
and then click through a normal member-area SPA flow. The login form's
selectors (input[type=email], input[type=password], a button whose
accessible name is exactly "登入") were read directly off the site's DOM
while logged in as the account owner, but could NOT be verified against a
*logged-out* session in the same sitting (navigating there while already
authenticated just redirects back -- there was no way to log out and back
in again without spending the account owner's login step a second time).
If the login step ever fails, check these selectors first before assuming
something more exotic (bot detection, changed markup) -- see
login_to_pressplay()'s diagnostics-on-failure for what to look at.

chengwaye.com/daily needs no login and no browser -- fetch_disposal.py
already proved a plain requests.get() with a browser-style User-Agent
works fine against this domain (unlike wantgoo.com), so this reuses that
exact same approach.

WHAT "族群" MEANS HERE: the source article maintains two running lists of
stock codes (occasionally names, per the article author's own admission
that these are sometimes mistyped) -- "目前沒找到族群" (no sector/theme group
identified yet) and "目前有發現有族群" (a group has been identified). This
script cross-references both lists against chengwaye.com/daily's own
AI-assigned 族群 (sector group) label for that stock, so you can see next
to each code whether chengwaye's independent classification agrees.

Usage:
    # full live run: logs into PressPlay, reads the latest premarket
    # article, fetches chengwaye.com/daily, matches, writes JSON to stdout
    PRESSPLAY_EMAIL=... PRESSPLAY_PASSWORD=... python fetch_pressplay_groups.py

    # offline test mode -- no network/browser needed for either half
    python fetch_pressplay_groups.py \
        --fixture-article ../fixtures/pressplay_article.txt \
        --fixture-daily ../fixtures/chengwaye_daily.html
"""
import argparse
import datetime
import difflib
import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    sync_playwright = None
    PlaywrightTimeoutError = Exception

LOGIN_URL = "https://www.pressplay.cc/member/login"
ARTICLES_URL = (
    "https://www.pressplay.cc/member/learning/projects/"
    "1002F3D338218A43A3A65E8D2A80376F/articles"
)
BASE_URL = "https://www.pressplay.cc"

DAILY_URL = "https://chengwaye.com/daily"
DAILY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

TAIPEI = datetime.timezone(datetime.timedelta(hours=8))


# ---------------------------------------------------------------------------
# PressPlay: login + find + read the latest premarket article
# ---------------------------------------------------------------------------

def login_to_pressplay(page, email: str, password: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

    email_input = page.locator('input[type="email"]')
    if email_input.count() == 0:
        # fallback -- see module docstring, selectors unverified logged-out
        email_input = page.locator('input[type="text"]')
    email_input.first.fill(email)
    page.locator('input[type="password"]').first.fill(password)

    login_button = page.get_by_role("button", name="登入", exact=True)
    if login_button.count() == 0:
        login_button = page.locator('button[type="submit"]')
    login_button.first.click()

    try:
        page.wait_for_url(lambda url: "/member/login" not in url, timeout=20000)
    except PlaywrightTimeoutError:
        debug = page.evaluate(
            """() => ({
                url: location.href,
                title: document.title,
                bodySnippet: document.body ? document.body.innerText.slice(0, 300) : null,
            })"""
        )
        raise RuntimeError(
            "PressPlay login did not redirect away from /member/login within "
            f"20s -- still stuck there, login likely failed (wrong "
            f"credentials, CAPTCHA, or the site blocked this automated "
            f"login -- see module docstring's KNOWN RISK). Page state: {debug}"
        )


def find_latest_premarket_article(page):
    """Returns (title, absolute_url) for the newest 盤前 (premarket) article
    in the project's article list, or (None, None) if none is found. The
    list renders newest-first (confirmed live, 2026-08-20), so this takes
    the first title containing 盤前 and NOT 盤後 -- no date parsing needed.
    """
    page.goto(ARTICLES_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector(".article-card", timeout=20000)

    cards = page.locator(".article-card")
    for i in range(cards.count()):
        header = cards.nth(i).locator(".article-card-header")
        if header.count() == 0:
            continue
        title = header.first.inner_text().strip()
        if "盤前" in title and "盤後" not in title:
            href = header.first.get_attribute("href")
            if not href:
                continue
            url = href if href.startswith("http") else BASE_URL + href
            return title, url
    return None, None


def read_article_text(page, url: str) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    # Client-side rendered SPA content -- wait for real text, not a fixed
    # delay (see tx_night_session.py's module docstring for why a fixed
    # wait_for_timeout was proven unreliable for this kind of page).
    page.wait_for_function(
        """() => {
            const el = document.querySelector('.article-content');
            return !!el && el.innerText.trim().length > 20;
        }""",
        timeout=15000,
    )
    return page.locator(".article-content").first.inner_text()


def fetch_article_via_browser():
    if sync_playwright is None:
        raise RuntimeError(
            "playwright is not installed -- run "
            "`playwright install --with-deps chromium` (see requirements.txt)"
        )
    email = os.environ.get("PRESSPLAY_EMAIL")
    password = os.environ.get("PRESSPLAY_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "PRESSPLAY_EMAIL / PRESSPLAY_PASSWORD are not set in the "
            "environment -- see module docstring: these must be set as "
            "GitHub Actions secrets by the repo owner, this script never "
            "prompts for or hardcodes them."
        )
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--disable-blink-features=AutomationControlled"]
        )
        try:
            page = browser.new_page(locale="zh-TW")
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            login_to_pressplay(page, email, password)
            title, url = find_latest_premarket_article(page)
            if not title:
                raise RuntimeError(
                    "no 盤前 article found in the project's article list -- "
                    "either the project has no premarket articles yet, or "
                    "the list markup changed (see find_latest_premarket_article)."
                )
            text = read_article_text(page, url)
            return {"title": title, "url": url}, text
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Parsing the article's two group-list sections
# ---------------------------------------------------------------------------

def parse_group_sections(text: str):
    """
    Returns (not_found_raw, found_raw) -- the raw text under each of the
    two section headers, before tokenizing. Header wording has been seen
    to vary slightly day to day ("目前沒找到族群" vs "目前沒有找到族群";
    "目前有發現有族群" vs "目前發現有族群") so both patterns tolerate the
    optional 有.
    """
    m1 = re.search(r"一[、，,]\s*目前沒(?:有)?找到族群[：:]\s*(.*?)(?=\n\s*二[、，,])", text, re.S)
    m2 = re.search(r"二[、，,]\s*目前(?:有)?發現有?族群[：:]\s*(.*?)(?=《|—{3,}|$)", text, re.S)
    not_found_raw = m1.group(1).strip() if m1 else ""
    found_raw = m2.group(1).strip() if m2 else ""
    return not_found_raw, found_raw


def tokenize_group_list(raw: str):
    """Splits a raw group-list blob into individual stock tokens (usually
    4-digit codes, occasionally names -- possibly mistyped, per the source
    article's own disclaimer). Empty/placeholder content (blank, or a
    literal '0' meaning "none today") returns an empty list rather than a
    bogus single token -- confirmed live 2026-08-20: section 二 read just
    "0" when nothing had been found that day.
    """
    raw = raw.strip()
    if not raw or raw in ("0", "無", "無資料", "-", "--"):
        return []
    parts = re.split(r"[.．,，、\s]+", raw)
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# chengwaye.com/daily: fetch + match
# ---------------------------------------------------------------------------

def fetch_daily_html() -> str:
    if requests is None:
        raise RuntimeError("requests not installed and no --fixture-daily given")
    resp = requests.get(DAILY_URL, headers=DAILY_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_daily_rows(html: str):
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required for this script")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    rows = []
    if table is not None:
        body = table.find("tbody") or table
        columns = [
            "market", "code", "name", "close", "volume",
            "foreign", "trust", "dealer", "ai_reason", "group",
        ]
        for tr in body.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) < len(columns):
                continue
            rows.append(dict(zip(columns, cells)))

    latest_date = None
    select_tag = soup.find("select", id="date-picker") or soup.find("select")
    if select_tag is not None:
        first_option = select_tag.find("option")
        if first_option is not None:
            latest_date = first_option.get_text(strip=True)

    return rows, latest_date


def match_token(token: str, rows):
    """Match one article token against chengwaye's daily rows: exact code,
    then exact name, then a typo-tolerant fuzzy name match. Returns a dict
    with match_type, or None if nothing clears the fuzzy-match confidence
    bar -- callers must surface unmatched tokens rather than dropping them
    (a wrong silent match on a financial ticker is worse than an honest
    "couldn't match this, check by hand").

    Known limitation (tested 2026-08-20): the 0.6 cutoff is deliberately
    conservative to avoid false-matching two different stocks, but that
    means a single mistyped character in a short 2-character name (e.g.
    "鼎元" -> "鼎緣") often does NOT clear it and falls through to
    unmatched -- each character carries too much weight in a 2-character
    string for any similarity metric to stay both safe and lenient. Typos
    in 3+ character names fuzzy-match reliably (tested: "中再保" ->
    "中再堡", "聯一光" -> "聯一先" both matched correctly). This is an
    accepted trade-off, not a bug: an honest "couldn't match, check by
    hand" beats a confident wrong guess on financial data.
    """
    token = token.strip()
    if not token:
        return None

    for row in rows:
        if row["code"] == token:
            return {**row, "match_type": "code", "raw_token": token}

    for row in rows:
        if row["name"] == token:
            return {**row, "match_type": "name", "raw_token": token}

    names = [r["name"] for r in rows]
    close = difflib.get_close_matches(token, names, n=1, cutoff=0.6)
    if close:
        matched_row = next(r for r in rows if r["name"] == close[0])
        return {**matched_row, "match_type": "fuzzy_name", "raw_token": token}

    return None


def match_section(raw_tokens, rows):
    matched, unmatched = [], []
    for token in raw_tokens:
        result = match_token(token, rows)
        if result is not None:
            matched.append(result)
        else:
            unmatched.append(token)
    return {"raw_tokens": raw_tokens, "matched": matched, "unmatched": unmatched}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fixture-article", type=Path, default=None,
        help="offline test: read article text from this file instead of logging into PressPlay",
    )
    ap.add_argument(
        "--fixture-daily", type=Path, default=None,
        help="offline test: read chengwaye.com/daily HTML from this file instead of the network",
    )
    args = ap.parse_args()

    now = datetime.datetime.now(TAIPEI)

    if args.fixture_article is not None:
        raw = args.fixture_article.read_text(encoding="utf-8")
        # fixture files carry a small header block (Title/URL/Source
        # element) before "---"; parse title/url out of it -- both for
        # test fidelity (the built page's "資料來源" footer needs a real
        # title to not show its empty state) and so this also accepts a
        # raw already-flattened dump with no header at all.
        title, url = None, None
        if "\n---\n" in raw:
            header, article_text = raw.split("\n---\n", 1)
            for line in header.splitlines():
                if line.startswith("Title:"):
                    title = line[len("Title:"):].strip()
                elif line.startswith("URL:"):
                    url = line[len("URL:"):].strip()
        else:
            article_text = raw
        source_article = {"title": title, "url": url, "fixture": str(args.fixture_article)}
    else:
        source_article, article_text = fetch_article_via_browser()

    source_article["collected_at"] = now.isoformat()

    not_found_raw, found_raw = parse_group_sections(article_text)
    not_found_tokens = tokenize_group_list(not_found_raw)
    found_tokens = tokenize_group_list(found_raw)

    if args.fixture_daily is not None:
        daily_html = args.fixture_daily.read_text(encoding="utf-8")
    else:
        daily_html = fetch_daily_html()
    daily_rows, chengwaye_latest_date = parse_daily_rows(daily_html)

    result = {
        "source_article": source_article,
        "chengwaye_date": chengwaye_latest_date,
        "not_found_group": match_section(not_found_tokens, daily_rows),
        "found_group": match_section(found_tokens, daily_rows),
    }

    total_unmatched = (
        len(result["not_found_group"]["unmatched"])
        + len(result["found_group"]["unmatched"])
    )
    if total_unmatched:
        print(
            f"WARNING: {total_unmatched} token(s) could not be matched to a "
            "chengwaye.com/daily row -- see *_group.unmatched in the output.",
            file=sys.stderr,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
