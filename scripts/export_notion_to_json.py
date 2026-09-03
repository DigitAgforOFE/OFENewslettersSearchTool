#!/usr/bin/env python3
"""
OFE Newsletters Search Tool — Notion -> data/database.json exporter
================================================================

WHAT THIS IS
------------
A portable, standalone version of the monthly export. In normal use you do
NOT need to run this yourself: you ask Claude (in a session connected to
your Notion account) to "run the monthly OFE Newsletters Search Tool
export," and Claude reads the database through its own Notion connection
and writes data/database.json directly. No credentials change hands that
way.

This script exists as a fallback / audit trail, a way to run the export
without Claude (e.g. from a scheduled GitHub Action), and as documentation
of exactly what the export logic does.

WHY THIS STEP DOESN'T ALSO DO MERGE/DEDUP
-------------------------------------------
The build brief's content pipeline (NEW / UPDATE / DUPLICATE / UNCERTAIN
classification) happens earlier, when a newsletter's items are first added
to Notion. That's already how this project works each month: extract items
-> tag them -> check them against what's already in Notion -> add or
update rows there. Notion is the continuously-merged, deduplicated
database the brief describes.

This script's job is narrower: take a fresh, complete snapshot of Notion's
current (already-merged) state and turn it into the public JSON. That's
Decision A from the earlier SOW (full rebuild, not incremental patching),
and it stays the simpler, safer choice specifically because the merge
already happened upstream in Notion. Re-implementing merge/dedup logic
here would be solving a problem that's already solved.

What this script DOES do to keep the brief's audit-trail intent (section
15, "human approval" / change report): it diffs the new export against the
most recent dated snapshot and prints/logs which IDs were added, removed,
or changed, so a monthly run still tells you what changed, without needing
a separate merge engine.

SETUP (only needed if you run this script directly, outside a Claude session)
-------------------------------------------------------------------------
1. pip install notion-client jsonschema
2. Create a Notion integration at https://www.notion.so/my-integrations,
   copy its "Internal Integration Secret."
3. Share the "OFE-C Resource Library" database with that integration
   (••• menu on the database -> Connections -> your integration).
4. Set the token as an environment variable, never paste it into this file:
       export NOTION_TOKEN="secret_..."
5. Run from the repo root:
       python3 scripts/export_notion_to_json.py

WHAT IT DOES
------------
1. Reads every row of the OFE-C Resource Library data source.
2. Keeps only fields safe to publish (internal-only fields like Curator
   notes and Duplicate status are deliberately left out).
3. Picks one public URL per item (the replacement if the original died,
   flagging Wayback Machine copies as "archived").
4. Flags "expired" for Job posting / Survey items whose publish date is
   more than EXPIRY_DAYS in the past.
5. Writes data/database.json (always overwritten, this is what the live
   page reads) and a dated snapshot data/database-YYYY-MM.json (kept for
   history, never overwritten).
6. Runs scripts/validate_data.py against the result. If validation fails,
   database.json is NOT touched, the previous valid version stays in
   place, per the brief's "if validation fails, do not publish" rule.
7. Prints a change report (added / removed / updated ids) versus the last
   snapshot, and appends one line to processing-log.json.
"""

import os
import sys
import json
import subprocess
import datetime
import glob
import hashlib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ROOT, "data")
DATABASE_PATH = os.path.join(DATA_DIR, "database.json")
LOG_PATH = os.path.join(ROOT, "processing-log.json")

DATA_SOURCE_ID = "61aed91d-d523-4747-b14b-3d13457ca5ce"
EXPIRY_DAYS = 90
TIME_BOUND_TYPES = {"Job posting", "Survey"}


def fetch_all_rows(client):
    rows = []
    cursor = None
    while True:
        kwargs = {"database_id": DATA_SOURCE_ID}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.databases.query(**kwargs)
        rows.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return rows


def prop_text(page, name):
    p = page["properties"].get(name)
    if not p:
        return None
    t = p["type"]
    if t == "title":
        return "".join(x["plain_text"] for x in p["title"]) or None
    if t == "rich_text":
        return "".join(x["plain_text"] for x in p["rich_text"]) or None
    if t == "url":
        return p["url"]
    if t == "select":
        return p["select"]["name"] if p["select"] else None
    if t == "multi_select":
        return [o["name"] for o in p["multi_select"]]
    if t == "number":
        return p["number"]
    if t == "date":
        return p["date"]["start"] if p["date"] else None
    return None


def resolve_url(item_url, replacement_url):
    if replacement_url:
        status = "archived" if "web.archive.org" in replacement_url else "alternate"
        return replacement_url, status
    if item_url:
        return item_url, "live"
    return None, "unavailable"


def parse_people(raw):
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    seen, out = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def build_item(page, today, generated_at):
    item_id = prop_text(page, "Item ID")
    item_url = prop_text(page, "Item URL")
    replacement_url = prop_text(page, "Replacement URL")
    content_type = prop_text(page, "Content Type")
    date_start = prop_text(page, "Date")
    url, url_status = resolve_url(item_url, replacement_url)

    expired = False
    if content_type in TIME_BOUND_TYPES:
        if date_start:
            try:
                d = datetime.date.fromisoformat(date_start[:10])
                expired = (today - d).days > EXPIRY_DAYS
            except ValueError:
                expired = True
        else:
            expired = True

    return {
        "id": item_id,
        "title": prop_text(page, "Title"),
        "summary": prop_text(page, "Summary"),
        "url": url,
        "urlStatus": url_status,
        "publishDate": date_start,
        "contentType": content_type,
        "topics": prop_text(page, "Topic tags") or [],
        "locations": prop_text(page, "Geography") or [],
        "croppingSystems": prop_text(page, "Cropping systems") or [],
        "people": parse_people(prop_text(page, "People / orgs")),
        "sourceNewsletter": prop_text(page, "Source newsletter"),
        "newsletterNo": prop_text(page, "Newsletter No."),
        "doi": prop_text(page, "DOI"),
        "publication": prop_text(page, "Publication"),
        "citations": prop_text(page, "Citations"),
        "createdAt": date_start,
        "updatedAt": generated_at,
        "expired": expired,
    }


def content_hash(item):
    keys = ["title", "summary", "url", "contentType", "topics", "locations", "croppingSystems", "publishDate"]
    blob = json.dumps({k: item.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def find_previous_snapshot():
    candidates = sorted(glob.glob(os.path.join(DATA_DIR, "database-*.json")))
    return candidates[-1] if candidates else None


def change_report(new_items, previous_path):
    if not previous_path or not os.path.exists(previous_path):
        return {"added": [], "removed": [], "updated": [], "note": "no previous snapshot to compare against"}
    with open(previous_path) as f:
        prev = json.load(f)
    prev_by_id = {i["id"]: i for i in prev.get("items", []) if i.get("id")}
    new_by_id = {i["id"]: i for i in new_items if i.get("id")}

    added = sorted(set(new_by_id) - set(prev_by_id))
    removed = sorted(set(prev_by_id) - set(new_by_id))
    updated = sorted(
        iid for iid in (set(new_by_id) & set(prev_by_id))
        if content_hash(new_by_id[iid]) != content_hash(prev_by_id[iid])
    )
    return {"added": added, "removed": removed, "updated": updated}


def main():
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        sys.exit(
            "NOTION_TOKEN is not set. Export a Notion integration secret as an "
            "environment variable first, see the setup notes at the top of this "
            "file. Never hardcode the token in this script."
        )
    try:
        from notion_client import Client
    except ImportError:
        sys.exit("Missing dependency. Run: pip install notion-client")

    client = Client(auth=token)
    today = datetime.date.today()
    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pages = fetch_all_rows(client)
    items = [build_item(p, today, generated_at) for p in pages]
    items = [i for i in items if i["id"]]
    items.sort(key=lambda x: (x["newsletterNo"] or 0, x["id"]))

    out = {
        "schemaVersion": "1.0",
        "generatedAt": generated_at,
        "version": today.isoformat(),
        "count": len(items),
        "items": items,
    }

    previous_path = find_previous_snapshot()
    report = change_report(items, previous_path)

    # Write to a temp file first, validate, then move into place. If
    # validation fails, the previous database.json is left untouched.
    tmp_path = DATABASE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "validate_data.py"), "--file", tmp_path, "--previous", previous_path or ""],
        cwd=ROOT,
    )
    if result.returncode != 0:
        os.remove(tmp_path)
        sys.exit("Validation failed, see errors above. database.json was NOT updated.")

    os.replace(tmp_path, DATABASE_PATH)
    snapshot_path = os.path.join(DATA_DIR, "database-{}.json".format(today.strftime("%Y-%m")))
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    log = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH) as f:
            log = json.load(f)
    log.append({
        "timestamp": generated_at,
        "itemCount": len(items),
        "missingUrl": sum(1 for i in items if not i["url"]),
        "expiredCount": sum(1 for i in items if i["expired"]),
        "snapshotFile": os.path.basename(snapshot_path),
        "changeReport": report,
    })
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=1)

    print("\nWrote data/database.json and {} ({} items)".format(os.path.basename(snapshot_path), len(items)))
    print("Change report vs {}:".format(os.path.basename(previous_path) if previous_path else "(none)"))
    print("  added:   {}".format(report.get("added") or "none"))
    print("  removed: {}".format(report.get("removed") or "none"))
    print("  updated: {}".format(report.get("updated") or "none"))


if __name__ == "__main__":
    main()
