#!/usr/bin/env python3
"""
Consistency checks for the pageKeywords enrichment, complementing
validate_data.py (which checks schema/structure, not enrichment quality).

This script never modifies data, it only reports. Run it before publishing
any pageKeywords change, especially after a manual (human-pasted) enrichment
pass, since those bypass the automated novelty filter in
enrich_search_keywords.py and can introduce inconsistencies a schema
validator wouldn't catch:
  - a keyword that duplicates something already in the item's own title/
    summary/tags (defeats the purpose: it adds no new search surface)
  - duplicate keywords within one item
  - pageKeywords / pageKeywordsUpdatedAt / pageKeywordsSource getting out
    of sync with each other
  - an unrecognized pageKeywordsSource value
  - copy-paste mojibake (encoding artifacts) surviving in any text field
  - a doi field that isn't a plausible DOI
  - a url that's still a tracking/wrapper link (Mimecast, list-manage,
    Cloudflare challenge tokens, etc.) rather than the real destination

USAGE
-----
    python3 scripts/check_page_keywords.py
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "database.json")

WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']*[a-zA-Z]")
VALID_SOURCE_RE = re.compile(r"^(scraped-page|manual|youtube-oembed|doi:.+|doi-title-match:.+)$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
MOJIBAKE_MARKERS = ["Ã©", "Ã¨", "Ã¢", "â€™", "â€œ", "â€\x9d", "Ã¯", "Ã±", "Â "]
WRAPPER_DOMAIN_MARKERS = ["mimecastprotect.com", "list-manage.com", "safelinks.protection.outlook.com"]
TRACKING_QUERY_MARKERS = ["__cf_chl_tk", "utm_source", "utm_campaign"]


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


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]

    issues = []
    doi_owners = {}

    for item in items:
        iid = item["id"]
        kw = item.get("pageKeywords")
        updated = item.get("pageKeywordsUpdatedAt")
        source = item.get("pageKeywordsSource")

        # 1. paired-field consistency
        has_kw = bool(kw)
        if has_kw != bool(updated):
            issues.append("{}: pageKeywords present={} but pageKeywordsUpdatedAt present={}".format(iid, has_kw, bool(updated)))
        if has_kw and not source:
            issues.append("{}: has pageKeywords but no pageKeywordsSource".format(iid))
        if source and not VALID_SOURCE_RE.match(source):
            issues.append("{}: unrecognized pageKeywordsSource '{}'".format(iid, source))

        if kw:
            # 2. cap
            if len(kw) > 20:
                issues.append("{}: {} keywords, over the 20 cap".format(iid, len(kw)))
            # 3. empty / whitespace entries
            for k in kw:
                if not k or not k.strip():
                    issues.append("{}: blank keyword entry".format(iid))
            # 4. within-item duplicates (case-insensitive)
            seen = {}
            for k in kw:
                key = k.strip().lower()
                if key in seen:
                    issues.append("{}: duplicate keyword '{}' / '{}'".format(iid, seen[key], k))
                else:
                    seen[key] = k
            # 5. novelty: keyword already present in the item's own known text
            known_words, known_blob = existing_vocab(item)
            for k in kw:
                key = k.strip().lower()
                if key and key in known_blob:
                    issues.append("{}: keyword '{}' already appears in this item's own title/summary/tags".format(iid, k))

        # 6. DOI plausibility
        doi_field = item.get("doi")
        if doi_field:
            for d in doi_field.split(";"):
                d = d.strip()
                if d and not DOI_RE.match(d):
                    issues.append("{}: doi '{}' doesn't look like a real DOI".format(iid, d))
                if d:
                    doi_owners.setdefault(d, []).append(iid)

        # 7. wrapper/tracking URLs left in place
        url = item.get("url") or ""
        for marker in WRAPPER_DOMAIN_MARKERS + TRACKING_QUERY_MARKERS:
            if marker in url:
                issues.append("{}: url still contains wrapper/tracking marker '{}': {}".format(iid, marker, url))

    # 8. mojibake scan across all string fields
    def walk_strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for v in obj.values():
                yield from walk_strings(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk_strings(v)

    for s in walk_strings(data):
        for marker in MOJIBAKE_MARKERS:
            if marker in s:
                issues.append("possible mojibake marker '{}' found in: {}".format(marker, s[:80]))
                break

    # 9. DOIs reused across more than one item (info, not necessarily wrong)
    shared = {d: ids for d, ids in doi_owners.items() if len(ids) > 1}

    print("Checked {} items.".format(len(items)))
    print("-" * 60)
    if issues:
        print("{} issue(s) found:".format(len(issues)))
        for i in issues:
            print("  [issue] " + i)
    else:
        print("No issues found.")
    if shared:
        print("-" * 60)
        print("{} DOI(s) shared by more than one item (verify intentional):".format(len(shared)))
        for d, ids in shared.items():
            print("  [info] {} -> {}".format(d, ids))
    print("-" * 60)
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
