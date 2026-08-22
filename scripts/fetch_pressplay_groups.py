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
original selectors (input[type=email], input[type=password], a button
whose accessible name is exactly "登入") were read directly off the site's
DOM while logged in as the account owner, but could NOT be verified
against a *logged-out* session in the same sitting (navigating there while
already authenticated just redirects back -- there was no way to log out
and back in again without spending the account owner's login step a
second time).

**2026-08-20, first live run (GitHub Actions, secrets newly set) --
confirmed failure, root-caused, hardened**: login_to_pressplay() timed out
after 30s waiting for input[type="text"] -- neither type=email nor
type=text matched a fillable field. Investigated (without ever touching
the account owner's real login form, which stays off-limits per the note
above): confirmed via an unauthenticated same-origin `fetch()` that
/member/login IS the correct URL and IS a real distinct page when logged
out (title "會員登入 - PressPlay Academy", not a redirect) -- so the URL
was never the problem. The server-rendered HTML for that page has zero
<input>/<form> elements: this is a fully client-rendered SPA (custom
webpack build, not Next/Nuxt) where the actual form only exists after the
JS bundles mount it. The fetched HTML also loads a `recaptcha` script on
this route, which is a real candidate for why an automated session could
get stuck even with the right selectors (see PROHIBITED actions this
project's operator will not attempt: solving or bypassing CAPTCHAs -- if
that turns out to be the actual blocker, this becomes a hard stop, not a
selector-tuning problem).

Hardened login_to_pressplay() in response: (1) added a `networkidle` wait
before searching, since the original `domcontentloaded` returns before an
SPA finishes mounting; (2) widened the field search from 2 guesses to a
list of 9 (by type, autocomplete, name substring, and Chinese/English
placeholder text), taking the first *visible* match; (3) every failure
mode now raises with a structural DOM snapshot (input count, and each
input's type/name/id/placeholder/visibility -- never values) via
_diagnose_page(), so the NEXT failure (if any) is self-diagnosing straight
from the GitHub Actions log instead of requiring another investigation
like this one. Not yet re-verified against a real logged-out run as of
this edit -- that's the next step, not a claim of a confirmed fix.

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

def _diagnose_page(page) -> dict:
    """Safe diagnostic snapshot for a failed PressPlay page interaction --
    structural info only (URL, title, input element attributes, visible
    body text), never field VALUES, so this is safe to surface in an
    exception message that ends up in a public GitHub Actions log even
    though real credentials were involved in the surrounding call. Added
    2026-08-20 after the first live run timed out waiting for
    input[type="text"] -- see the 2026-08-20 note in the module docstring.
    """
    try:
        return page.evaluate(
            """() => ({
                url: location.href,
                title: document.title,
                inputCount: document.querySelectorAll('input').length,
                inputs: Array.from(document.querySelectorAll('input')).slice(0, 15).map(el => ({
                    type: el.type, name: el.name, id: el.id,
                    placeholder: el.placeholder,
                    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                })),
                bodySnippet: document.body ? document.body.innerText.slice(0, 200) : null,
            })"""
        )
    except Exception as exc:  # noqa: BLE001 -- diagnostics must never raise
        return {"diagnose_error": str(exc)}


# Tried in order; first VISIBLE match wins. Broadened 2026-08-20 after the
# original input[type=email] -> input[type=text] pair both failed to
# resolve on a real (logged-out, GitHub-Actions-run) attempt -- see the
# module docstring's 2026-08-20 note for why the original two-selector
# guess wasn't verifiable ahead of time, and _diagnose_page() above for
# what a future failure now reports instead of a bare timeout.
_EMAIL_INPUT_SELECTORS = [
    'input[type="email"]',
    'input[autocomplete="username"]',
    'input[autocomplete="email"]',
    'input[name*="email" i]',
    'input[name*="account" i]',
    'input[placeholder*="Email" i]',
    'input[placeholder*="帳號"]',
    'input[placeholder*="信箱"]',
    'input[type="text"]',
]
_PASSWORD_INPUT_SELECTORS = [
    'input[type="password"]',
    'input[autocomplete="current-password"]',
]


def _first_visible_input(page, selectors):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            count = loc.count()
        except Exception:  # noqa: BLE001 -- a bad selector shouldn't abort the search
            count = 0
        for i in range(count):
            candidate = loc.nth(i)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:  # noqa: BLE001
                continue
    return None


def login_to_pressplay(page, email: str, password: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    # This is a client-rendered SPA (confirmed 2026-08-20: the server HTML
    # has zero <input>/<form> elements: everything mounts after the JS
    # bundles run) -- give it a chance to settle before searching. Not
    # fatal if the site never truly goes idle (analytics beacons etc. can
    # prevent that); the widened selector search below still applies its
    # own timeout.
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    try:
        page.wait_for_selector("input", timeout=20000)
    except PlaywrightTimeoutError:
        debug = _diagnose_page(page)
        raise RuntimeError(
            "PressPlay login page never rendered a single <input> element "
            f"within 20s -- see KNOWN RISK in the module docstring (CAPTCHA "
            f"or bot detection are candidates given this page loads a "
            f"reCAPTCHA script). Page state: {debug}"
        )

    email_input = _first_visible_input(page, _EMAIL_INPUT_SELECTORS)
    password_input = _first_visible_input(page, _PASSWORD_INPUT_SELECTORS)
    if email_input is None or password_input is None:
        debug = _diagnose_page(page)
        raise RuntimeError(
            "PressPlay login form fields not found by any known selector "
            f"(email_found={email_input is not None}, "
            f"password_found={password_input is not None}) -- the real "
            f"input list is in the page state below; update "
            f"_EMAIL_INPUT_SELECTORS / _PASSWORD_INPUT_SELECTORS to match. "
            f"Page state: {debug}"
        )
    email_input.fill(email)
    password_input.fill(password)

    login_button = page.get_by_role("button", name="登入", exact=True)
    if login_button.count() == 0:
        login_button = page.locator('button[type="submit"]')
    if login_button.count() == 0:
        login_button = page.get_by_role(
            "button", name=re.compile("登入|Login|Sign in", re.IGNORECASE)
        )
    login_button.first.click()

    try:
        page.wait_for_url(lambda url: "/member/login" not in url, timeout=20000)
    except PlaywrightTimeoutError:
        debug = _diagnose_page(page)
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

    email = os.getenv("PRESSPLAY_EMAIL")
    password = os.getenv("PRESSPLAY_PASSWORD")

    # Local fallback candidates
    today_str = now.strftime("%Y-%m-%d")
    local_md = Path(f"data/pressplay/{today_str}.md")
    fixture_txt = Path("fixtures/pressplay_article.txt")

    if args.fixture_article is not None:
        fixture_file = args.fixture_article
    elif not email or not password:
        if local_md.exists():
            fixture_file = local_md
        elif fixture_txt.exists():
            fixture_file = fixture_txt
        else:
            fixture_file = None
    else:
        fixture_file = None

    if fixture_file is not None and fixture_file.exists():
        raw = fixture_file.read_text(encoding="utf-8")
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
        source_article = {"title": title or "PressPlay 盤前整理文章", "url": url, "fixture": str(fixture_file)}
    elif email and password:
        try:
            source_article, article_text = fetch_article_via_browser()
        except Exception as e:
            print(f"PressPlay browser fetch failed: {e}, falling back to empty", file=sys.stderr)
            source_article, article_text = {"title": "PressPlay 整理文章 (載入失敗)", "url": None}, ""
    else:
        source_article, article_text = {"title": "PressPlay 整理文章 (無登入憑證)", "url": None}, "" 

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
