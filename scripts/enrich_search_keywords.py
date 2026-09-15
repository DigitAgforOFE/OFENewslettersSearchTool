#!/usr/bin/env python3
"""
Enrich data/database.json with keywords scraped from each item's linked page.

Why: search.js only matches against title/summary/topics/contentType/
locations/croppingSystems/people, all of which live inside the newsletter
text itself. Someone searching for a word that only appears on the linked
web page (an author's name, a specific technique, an organization) gets no
hit even though the resource is clearly relevant. This script visits each
item's `url`, pulls out distinctive terms from that page, and stores the
NEW ones (anything not already covered by the item's own fields) in a new
`pageKeywords` array field. search.js then includes that field in its
search haystack. Nothing about the visible cards changes.

This never overwrites `pageKeywords` for an item that failed on this run,
so re-running is safe/incremental. Pass --force to re-fetch everything.

SETUP
-----
    pip install requests beautifulsoup4 pypdf

USAGE
-----
    python3 scripts/enrich_search_keywords.py [--limit N] [--force] [--only ID,ID,...]

Writes data/database.json in place (pretty-printed, same layout) and a
report to scripts/enrichment_report.json listing every item that failed or
came back with little/no usable text, with a reason, for manual follow-up.
"""

import argparse
import json
import os
import re
import sys
import time
import collections

import requests
from bs4 import BeautifulSoup, Comment

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "database.json")
REPORT_PATH = os.path.join(ROOT, "scripts", "enrichment_report.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
}
TIMEOUT = 20
MAX_PDF_PAGES = 20
SLEEP_BETWEEN = 0.6
MIN_BODY_CHARS = 300
MIN_META_CHARS = 60
MAX_KEYWORDS = 20

STOPWORDS = set("""
a about above after again against all am an and any are aren't as at be
because been before being below between both but by can't cannot could
couldn't did didn't do does doesn't doing don't down during each few for
from further had hadn't has hasn't have haven't having he he'd he'll he's
her here here's hers herself him himself his how how's i i'd i'll i'm i've
if in into is isn't it it's its itself let's me more most mustn't my
myself no nor not of off on once only or other ought our ours ourselves
out over own same shan't she she'd she'll she's should shouldn't so some
such than that that's the their theirs them themselves then there there's
these they they'd they'll they're they've this those through to too under
until up very was wasn't we we'd we'll we're we've were weren't what
what's when when's where where's which while who who's whom why why's
with won't would wouldn't you you'd you'll you're you've your yours
yourself yourselves also within upon toward towards across per via using
use used one two three new like may might well many much still even
will shall must want wants wanted create created creates need needs
needed get gets getting got make makes making made please provide
provides provided providing include includes including available based
without however therefore thus etc first last next previous every
""".split())

# Site chrome / legal / navigation noise that shows up on almost every page
# and would otherwise pollute every single item's keyword list.
BOILERPLATE_NOISE = set("""
home about contact us privacy policy cookie cookies terms conditions
service services login log sign signin signup subscribe newsletter
follow us share print download menu search skip content copyright
rights reserved read more learn more click here back top navigation
accept decline settings preferences language english site map footer
header advertisement advertise sponsored related articles comments
comment reply email address password username submit cancel close
loading please wait javascript enable browser cookies required
google apple scholar customers prospects employees users people account
accounts help support faq feedback rating ratings review reviews social
media facebook twitter instagram youtube linkedin pinterest whatsapp
""".split())

# Must end in a letter (not '-'/''): a line-wrapped PDF/HTML hyphenation like
# "conference-" would otherwise pass through as its own bogus "word".
WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']*[a-zA-Z]")
CAP_PHRASE_RE = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\b")

BLOCK_MARKERS = [
    "sign in to linkedin", "join linkedin", "enable javascript",
    "please verify you are a human", "access denied", "403 forbidden",
    "just a moment", "checking your browser", "captcha",
]


def log(msg):
    print(msg, flush=True)


def fetch(url):
    """Returns (kind, payload, final_url) where kind is 'html'/'pdf', or raises.

    web.archive.org occasionally serves a small "Wayback Machine" JS loader
    shim instead of the actual archived bytes on the first request (a
    timing/cache-miss flake, not a permanent failure) — retry a couple of
    times when that happens for a URL that should be a real PDF."""
    for attempt in range(3):
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "").lower()
        looks_like_pdf = "pdf" in ctype or resp.url.lower().endswith(".pdf")
        if looks_like_pdf:
            if resp.content[:5] == b"%PDF-":
                return "pdf", resp.content, resp.url
            if "web.archive.org" in url and attempt < 2:
                time.sleep(2)
                continue
            return "pdf", resp.content, resp.url
        return "html", resp.text, resp.url


def text_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_bits = []
    for name in ("description", "og:description", "og:title", "keywords"):
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            meta_bits.append(tag["content"])

    body = soup.get_text(separator=" ")
    body = re.sub(r"\s+", " ", body).strip()
    meta_text = re.sub(r"\s+", " ", " ".join([title] + meta_bits)).strip()
    full_text = meta_text + " " + body
    return full_text, body, meta_text


def text_from_pdf(data):
    from pypdf import PdfReader
    from io import BytesIO
    reader = PdfReader(BytesIO(data))
    chunks = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    text = re.sub(r"\s+", " ", " ".join(chunks)).strip()
    return text, text, text


def looks_blocked(text):
    low = text.lower()
    return any(marker in low for marker in BLOCK_MARKERS)


def existing_vocab(item):
    parts = [
        item.get("title") or "",
        item.get("summary") or "",
        " ".join(item.get("topics") or []),
        item.get("contentType") or "",
        " ".join(item.get("locations") or []),
        " ".join(item.get("croppingSystems") or []),
        " ".join(item.get("people") or []),
        item.get("sourceNewsletter") or "",
    ]
    blob = " ".join(parts).lower()
    return set(WORD_RE.findall(blob)), blob


def extract_keywords(full_text, raw_body, item):
    known_words, known_blob = existing_vocab(item)

    words = [w.lower() for w in WORD_RE.findall(full_text)]
    filtered = [w for w in words if len(w) >= 4 and w not in STOPWORDS and w not in BOILERPLATE_NOISE
                and w not in known_words and not w.isdigit()]

    unigram_counts = collections.Counter(filtered)
    bigram_counts = collections.Counter()
    for a, b in zip(filtered, filtered[1:]):
        bigram_counts[a + " " + b] += 1

    candidates = []
    for word, count in unigram_counts.most_common(60):
        if count >= 2:
            candidates.append((count + 0.1, word))
    for phrase, count in bigram_counts.most_common(40):
        if count >= 2:
            candidates.append((count + 0.2, phrase))

    # Capitalized multi-word phrases from the ORIGINAL-case text: catches proper
    # nouns (people, orgs, place names, product/technique names) that the plain
    # frequency pass above would miss since each word alone might be common.
    cap_counts = collections.Counter()
    for m in CAP_PHRASE_RE.finditer(full_text):
        phrase = m.group(0).strip()
        low = phrase.lower()
        if low in known_blob or len(phrase) < 5:
            continue
        words_in_phrase = phrase.lower().split()
        if all(w in STOPWORDS or w in BOILERPLATE_NOISE for w in words_in_phrase):
            continue
        cap_counts[phrase] += 1
    for phrase, count in cap_counts.most_common(30):
        if count >= 2 and phrase.lower() not in known_words:
            candidates.append((count + 0.3, phrase))

    # Dedupe case-insensitively, keep highest score, then rank and cap.
    best = {}
    for score, term in candidates:
        key = term.lower()
        if key not in known_blob and (key not in best or score > best[key][0]):
            best[key] = (score, term)

    ranked = sorted(best.values(), key=lambda x: -x[0])
    return [term for _, term in ranked[:MAX_KEYWORDS]]


DOI_URL_RE = re.compile(r"doi\.org/(.+)$", re.IGNORECASE)


def resolve_dois(item):
    """DOI(s) for this item. Usually one, but a handful of digest items
    ("Recent papers on OFE" and the like, see citedPapers() in search.js)
    bundle several papers into a ';'-separated `doi` field — pull keywords
    from all of them, not just the first, or a two-paper digest ends up
    only reflecting one paper's topic."""
    dois = [d.strip() for d in (item.get("doi") or "").split(";") if d.strip()]
    if dois:
        return dois
    url = item.get("url") or ""
    m = DOI_URL_RE.search(url)
    return [m.group(1)] if m else []


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    positions = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def strip_jats(text):
    return re.sub(r"<[^>]+>", " ", text or "")


def keywords_from_dois(dois, item):
    """Scholarly metadata APIs instead of the publisher page: these are free,
    not bot-blocked, and often better than scraped HTML (curated subject
    concepts rather than boilerplate). Tries OpenAlex first (richer:
    concepts + keywords + reconstructable abstract), falls back to Crossref
    (title + subjects + container-title + abstract, when Crossref has one).
    A digest item lists several DOIs; phrases from every one are merged."""
    known_words, known_blob = existing_vocab(item)
    phrases = []
    for doi in dois:
        phrases += _fetch_doi_phrases(doi, known_words)

    best = {}
    for term in phrases:
        term = (term or "").strip()
        key = term.lower()
        if term and key not in known_blob and key not in best:
            best[key] = term
    return list(best.values())[:MAX_KEYWORDS]


def _fetch_doi_phrases(doi, known_words):
    phrases = []
    abstract_text = ""

    try:
        r = requests.get("https://api.openalex.org/works/doi:{}".format(doi),
                          headers={"User-Agent": "OFE-Newsletters-Search-Tool/1.0"}, timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            # OpenAlex's ML-tagged concepts are noisy at low confidence/top
            # generic fields (level 0 "Business", "Engineering", ...) — a
            # thin record like a book chapter can tag "Popularity" at 0.58.
            # score>=0.5 + level>=1 keeps only the well-supported, non-generic
            # ones; strip the "(disambiguator)" suffix OpenAlex appends to
            # ambiguous terms (e.g. "Field (mathematics)" -> "Field").
            for c in d.get("concepts") or []:
                if c.get("score", 0) >= 0.5 and c.get("level", 0) >= 1:
                    name = re.sub(r"\s*\([^)]*\)\s*$", "", c.get("display_name", "")).strip()
                    if name:
                        phrases.append(name)
            abstract_text = reconstruct_abstract(d.get("abstract_inverted_index"))
    except Exception:
        pass

    if not phrases and not abstract_text:
        try:
            r = requests.get("https://api.crossref.org/works/{}".format(doi), timeout=TIMEOUT)
            if r.status_code == 200:
                msg = r.json().get("message", {})
                phrases += msg.get("subject") or []
                container = (msg.get("container-title") or [None])[0]
                if container:
                    phrases.append(container)
                abstract_text = strip_jats(msg.get("abstract"))
        except Exception:
            pass

    if abstract_text:
        words = [w.lower() for w in WORD_RE.findall(abstract_text)]
        filtered = [w for w in words if len(w) >= 4 and w not in STOPWORDS and w not in BOILERPLATE_NOISE
                    and w not in known_words and not w.isdigit()]
        for word, count in collections.Counter(filtered).most_common(15):
            if count >= 2:
                phrases.append(word)

    return phrases


def keywords_from_youtube(url, item):
    """oEmbed gives a clean, reliable video title + channel name without
    needing JS. YouTube's plain-HTML og:description is generic site
    boilerplate ("Enjoy the videos and music you love..."), not the real
    video description, so we deliberately don't scrape the page itself."""
    known_words, known_blob = existing_vocab(item)
    try:
        r = requests.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        d = r.json()
    except Exception:
        return []

    text = (d.get("title") or "") + " " + (d.get("author_name") or "")
    words = [w.lower() for w in WORD_RE.findall(text)]
    filtered = [w for w in words if len(w) >= 4 and w not in STOPWORDS and w not in BOILERPLATE_NOISE and w not in known_words]

    candidates = []
    if d.get("author_name") and d["author_name"].lower() not in known_blob:
        candidates.append(d["author_name"])
    for m in CAP_PHRASE_RE.finditer(d.get("title") or ""):
        phrase = m.group(0).strip()
        if phrase.lower() not in known_blob and len(phrase) >= 4:
            candidates.append(phrase)
    candidates += [w for w in filtered if w not in known_blob]

    best = {}
    for term in candidates:
        key = term.lower()
        if key not in known_blob and key not in best:
            best[key] = term
    # Drop single words already covered by a longer phrase we kept (e.g. the
    # author name "Jeff Hamlin" makes the standalone "jeff"/"hamlin" tokens redundant).
    phrases_text = " ".join(t.lower() for t in best.values() if " " in t)
    deduped = [t for t in best.values() if " " in t or t.lower() not in phrases_text.split()]
    return deduped[:MAX_KEYWORDS]


def process_item(item):
    url = item.get("url")
    result = {"id": item["id"], "url": url}
    domain = re.sub(r"^www\.", "", (requests.utils.urlparse(url).netloc or "").lower())

    dois = resolve_dois(item)
    if dois:
        keywords = keywords_from_dois(dois, item)
        if keywords:
            result["status"] = "ok"
            result["keywords"] = keywords
            result["via"] = "doi:{}".format(",".join(dois))
            return result

    if domain in ("youtube.com", "m.youtube.com", "youtu.be"):
        keywords = keywords_from_youtube(url, item)
        if keywords:
            result["status"] = "ok"
            result["keywords"] = keywords
            result["via"] = "youtube-oembed"
            return result

    try:
        kind, payload, final_url = fetch(url)
    except Exception as e:
        result["status"] = "failed"
        result["reason"] = "{}: {}".format(type(e).__name__, e)
        return result

    try:
        if kind == "pdf":
            full_text, raw_body, meta_text = text_from_pdf(payload)
        else:
            full_text, raw_body, meta_text = text_from_html(payload)
    except Exception as e:
        result["status"] = "failed"
        result["reason"] = "extract error: {}: {}".format(type(e).__name__, e)
        return result

    if looks_blocked(full_text):
        result["status"] = "blocked"
        result["reason"] = "page content indicates a login wall / bot check"
        return result

    # Some sites (Cornell CALS, for one) render the actual body client-side but
    # still server-render a real, specific <meta name="description"> for SEO —
    # that's worth keeping even when the visible body text is thin. Only the
    # body-and-meta-both-thin case is a genuine dead end.
    if len(raw_body) < MIN_BODY_CHARS and len(meta_text) < MIN_META_CHARS:
        result["status"] = "low_yield"
        result["reason"] = "only {} chars of body text extracted (thin/JS-rendered page?)".format(len(raw_body))
        result["charCount"] = len(raw_body)
        return result

    keywords = extract_keywords(full_text, raw_body, item)
    if not keywords:
        result["status"] = "low_yield"
        result["reason"] = "no novel keywords found (page text largely overlaps existing tags/summary)"
        result["charCount"] = len(raw_body)
        return result

    result["status"] = "ok"
    result["keywords"] = keywords
    result["finalUrl"] = final_url if final_url != url else None
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="re-fetch items that already have pageKeywords")
    ap.add_argument("--only", type=str, default=None, help="comma-separated item ids")
    ap.add_argument("--sleep", type=float, default=SLEEP_BETWEEN, help="seconds between requests (raise this for retries after 429s)")
    args = ap.parse_args()

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]
    by_id = {i["id"]: i for i in items}

    only_ids = set(args.only.split(",")) if args.only else None

    targets = []
    for item in items:
        if not item.get("url"):
            continue
        if only_ids and item["id"] not in only_ids:
            continue
        if not args.force and "pageKeywords" in item:
            continue
        targets.append(item)
    if args.limit:
        targets = targets[: args.limit]

    log("Processing {} of {} items with a URL...".format(len(targets), sum(1 for i in items if i.get("url"))))

    report = {"ok": [], "failed": [], "blocked": [], "low_yield": []}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for n, item in enumerate(targets, 1):
        log("[{}/{}] {} {}".format(n, len(targets), item["id"], item["url"]))
        result = process_item(item)
        status = result["status"]
        report[status].append(result)

        target = by_id[item["id"]]
        if status == "ok":
            target["pageKeywords"] = result["keywords"]
            target["pageKeywordsUpdatedAt"] = now
            target["pageKeywordsSource"] = result.get("via", "scraped-page")
            via = " [via {}]".format(result["via"]) if result.get("via") else ""
            log("    -> {} keyword(s){}: {}".format(len(result["keywords"]), via, ", ".join(result["keywords"][:8])))
        else:
            log("    -> {}: {}".format(status, result["reason"]))

        time.sleep(args.sleep)

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"runAt": now, "summary": {k: len(v) for k, v in report.items()}, "detail": report}, f, indent=2, ensure_ascii=False)

    log("\nDone. ok={} failed={} blocked={} low_yield={}".format(
        len(report["ok"]), len(report["failed"]), len(report["blocked"]), len(report["low_yield"])))
    log("Report written to {}".format(REPORT_PATH))


if __name__ == "__main__":
    main()
