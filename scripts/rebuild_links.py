#!/usr/bin/env python3
"""
Recover the links that items with more than one hyperlink were losing.

Background: the original per-newsletter extraction (../../extraction_v2_offline.json,
one level up from this repo) captured every link in each item's body correctly,
in reading order, with its anchor text. But everything downstream of that only
ever carried a single URL per item (Notion's "Item URL" + "Replacement URL"
columns, then database.json's single `url` field) so an item with two or more
links quietly lost all but one. Worse, if only one of an item's links needed a
dead-link replacement, resolve_url() in export_notion_to_json.py let that
replacement steal the primary slot from a different, still-live link.

Notion is no longer the source of truth for this project, so this script
bypasses it entirely: it merges the per-item link lists straight from
extraction_v2_offline.json with the per-URL dead-link research already done in
the "Links" sheet of OFE-C_Items_Extraction_v2.xlsx (../../OFE-C_Items_Extraction_v2.xlsx),
and writes the result into data/database.json as a new `links` array per item
(each entry: {url, anchorText, urlStatus}). item.url/urlStatus are kept as
before for backward compatibility, but now set from links[0] so a replacement
for one link can no longer clobber a different link's still-live URL.

Usage: python3 scripts/rebuild_links.py [--dry-run]
"""

import argparse
import json
import os
import sys
import urllib.parse

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(ROOT)
EXTRACTION_JSON = os.path.join(PROJECT_ROOT, "extraction_v2_offline.json")
LINKS_XLSX = os.path.join(PROJECT_ROOT, "OFE-C_Items_Extraction_v2.xlsx")
DATABASE_JSON = os.path.join(ROOT, "data", "database.json")

# "Primary" (item.url/urlStatus, used by the title link and the single-link
# "View resource" button) defaults to links[0] - the first link mentioned in
# reading order. That's usually right, but not always: a newsletter blurb
# can mention an aside (a book, a related tool) before the thing the item is
# actually about. Override per item_id here with the url of the link that
# should be primary instead; the full links[] array (and its reading order,
# which inline hyperlinking relies on) is untouched.
PRIMARY_OVERRIDES = {
    # "Inspiring from Other Sectors: What Medical Case Reporting Can Teach
    # OFE" - the item is about the Nissen & Wynn clinical-case-report paper
    # (matches item.doi); the Book of Why is a passing aside mentioned
    # earlier in the text, not the item's subject.
    "OFE-284": "https://link.springer.com/article/10.1186/1756-0500-7-264",
}


def unwrap_safelink(href):
    """Outlook wraps links as safelinks.protection.outlook.com/?url=<encoded>.
    The Links sheet records the real destination, not the wrapper, so unwrap
    before looking it up."""
    if "safelinks.protection.outlook.com" not in href:
        return href
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    inner = qs.get("url", [None])[0]
    return inner or href


def load_url_resolutions():
    """Return {url: (finalUrl_or_None, urlStatus)} built from the Links sheet.

    finalUrl is None when the link should be dropped (confirmed dead with no
    usable replacement, or explicitly marked "safe to drop").
    """
    wb = openpyxl.load_workbook(LINKS_XLSX, read_only=True, data_only=True)
    ws = wb["Links"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}

    resolutions = {}
    for r in rows[1:]:
        url = r[idx["URL"]]
        if not url:
            continue
        status = (r[idx["Status"]] or "").strip().lower()
        recovery = (r[idx["Recovery"]] or "").strip().lower()
        replacement = r[idx["Replacement URL"]]

        if replacement:
            final = replacement
            final_status = "archived" if "web.archive.org" in replacement else "alternate"
        elif recovery == "safe to drop" or status in (
            "unresolvable wrapper", "unreachable", "email contact, not a link",
        ) or status.startswith("dead (domain hijacked)"):
            final = None
            final_status = "unavailable"
        elif status.startswith("live") or status in ("closed",) or status.startswith("gated"):
            final = url
            final_status = "live"
        elif status.startswith("dead"):
            # A dead link with no replacement and no explicit drop verdict:
            # keep it out rather than publish a known-dead URL.
            final = None
            final_status = "unavailable"
        else:
            final = url
            final_status = "live"

        resolutions[url] = (final, final_status)

    return resolutions


def resolve_link(href, resolutions):
    """Look up href (unwrapping Outlook safelinks first). Falls back to
    publishing the href as-is, marked live, for the handful of URLs that
    never made it into the Links sheet (verified: none were flagged dead)."""
    candidates = [href]
    unwrapped = unwrap_safelink(href)
    if unwrapped != href:
        candidates.append(unwrapped)

    for c in candidates:
        if c in resolutions:
            return resolutions[c]

    return (unwrapped, "live")


def build_item_links(record, resolutions):
    links = []
    for raw in record.get("links", []):
        # extraction_v2_offline.json's `url` is href already resolved to an
        # absolute address (relative paths against the newsletter's domain,
        # Outlook safelinks unwrapped) - prefer it over the raw `href`.
        candidate = raw.get("url") or raw["href"]
        final_url, status = resolve_link(candidate, resolutions)
        if not final_url:
            continue
        links.append({
            "url": final_url,
            "anchorText": raw.get("anchor_text") or "",
            "urlStatus": status,
        })
    return links


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, don't write")
    args = parser.parse_args()

    resolutions = load_url_resolutions()

    with open(EXTRACTION_JSON, "r", encoding="utf-8") as f:
        extraction = json.load(f)
    records_by_id = {r["item_id"]: r for r in extraction["records"]}

    with open(DATABASE_JSON, "r", encoding="utf-8") as f:
        db = json.load(f)

    changed = 0
    multi_link_items = 0
    primary_url_fixed = 0

    for item in db["items"]:
        record = records_by_id.get(item["id"])
        if not record:
            continue

        links = build_item_links(record, resolutions)
        if not links:
            continue

        if links != item.get("links"):
            changed += 1
        item["links"] = links
        if len(links) > 1:
            multi_link_items += 1

        primary = links[0]
        override_url = PRIMARY_OVERRIDES.get(item["id"])
        if override_url:
            primary = next((l for l in links if l["url"] == override_url), primary)

        if item.get("url") != primary["url"] or item.get("urlStatus") != primary["urlStatus"]:
            primary_url_fixed += 1
        item["url"] = primary["url"]
        item["urlStatus"] = primary["urlStatus"]

    print("items updated with links[]: {}".format(changed))
    print("items with >1 link: {}".format(multi_link_items))
    print("items whose primary url/urlStatus changed: {}".format(primary_url_fixed))

    if args.dry_run:
        print("--dry-run: not writing " + DATABASE_JSON)
        return

    with open(DATABASE_JSON, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("wrote " + DATABASE_JSON)


if __name__ == "__main__":
    main()
