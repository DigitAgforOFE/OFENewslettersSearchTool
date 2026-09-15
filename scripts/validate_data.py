#!/usr/bin/env python3
"""
Validate data/database.json before it gets published.

Per the build brief (section 16): if validation fails, DO NOT PUBLISH.
The previous valid version stays live. This script never overwrites
anything, it only reads and reports, exit code 0 means "safe to commit,"
non-zero means "stop, fix the data first."

SETUP
-----
    pip install jsonschema

USAGE
-----
    python3 scripts/validate_data.py
    python3 scripts/validate_data.py --file data/database.json --previous data/database-2026-08.json

With no --previous given, the script looks for the most recent
data/database-*.json snapshot other than the file being checked, so the
"existing records preserved" check still runs by default.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(ROOT, "data", "database.json")
DEFAULT_SCHEMA = os.path.join(ROOT, "schema", "database.schema.json")

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"secret_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
INTERNAL_ONLY_KEYS = {
    "curator notes", "curatornotes", "duplicate status", "duplicatestatus",
    "internal notes", "internalnotes",
}


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def ok(self):
        return not self.errors


def load_json(path, report, label):
    if not os.path.exists(path):
        report.error("{}: file not found at {}".format(label, path))
        return None
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        report.error("{}: not valid JSON ({})".format(label, e))
        return None


def check_schema(data, report):
    try:
        import jsonschema
    except ImportError:
        report.warn("jsonschema package not installed (pip install jsonschema), skipping formal schema check")
        return
    if not os.path.exists(DEFAULT_SCHEMA):
        report.warn("schema file not found at {}, skipping formal schema check".format(DEFAULT_SCHEMA))
        return
    with open(DEFAULT_SCHEMA) as f:
        schema = json.load(f)
    validator = jsonschema.Draft7Validator(schema)
    errs = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    for e in errs[:25]:
        path = "/".join(str(p) for p in e.path) or "(root)"
        report.error("schema: {} -- {}".format(path, e.message))
    if len(errs) > 25:
        report.error("schema: {} more errors not shown".format(len(errs) - 25))


def check_structure(data, report):
    if "items" not in data or not isinstance(data["items"], list):
        report.error("structure: top-level 'items' array is missing")
        return []
    items = data["items"]

    if "count" in data and data["count"] != len(items):
        report.error(
            "structure: count field says {} but items array has {} entries"
            .format(data["count"], len(items))
        )

    return items


def check_ids(items, report):
    ids = [i.get("id") for i in items]
    missing = sum(1 for x in ids if not x)
    if missing:
        report.error("ids: {} item(s) have no id".format(missing))

    seen = {}
    for idx, i in enumerate(items):
        iid = i.get("id")
        if not iid:
            continue
        if iid in seen:
            report.error("ids: duplicate id '{}' at items[{}] and items[{}]".format(iid, seen[iid], idx))
        else:
            seen[iid] = idx


def check_required_fields(items, report):
    required = ["id", "title", "summary", "contentType", "topics", "locations", "croppingSystems"]
    for idx, i in enumerate(items):
        for field in required:
            if field not in i:
                report.error("required-fields: items[{}] ({}) missing '{}'".format(idx, i.get("id", "?"), field))
        if not (i.get("title") or "").strip():
            report.error("required-fields: items[{}] ({}) has an empty title".format(idx, i.get("id", "?")))


def check_dates(items, report):
    for i in items:
        for field in ("publishDate", "createdAt"):
            v = i.get(field)
            if v and not DATE_RE.match(v):
                report.error("dates: {} field '{}' on {} doesn't look like YYYY-MM-DD".format(field, v, i.get("id")))


def check_urls(items, report):
    for i in items:
        url = i.get("url")
        status = i.get("urlStatus")
        if url is None:
            if status != "unavailable":
                report.warn("urls: {} has no url but urlStatus is '{}', expected 'unavailable'".format(i.get("id"), status))
            continue
        if not URL_RE.match(url):
            report.error("urls: {} has a url that isn't http(s): {}".format(i.get("id"), url))


CONTENT_TYPES = {
    "Article or paper", "Report or guide", "Project or network profile", "Event",
    "Community notice", "Video", "Call for papers", "Tools of OFE", "Job posting",
    "Survey", "Podcast", "Award",
}
TOPICS = {
    "Farmer engagement & co-design", "Community building", "Experimental design & methodology",
    "Networks & platforms", "Sustainability/SDGs", "Data analysis tools", "AgTech & AI",
    "Data governance & sharing", "Soil health", "Policy",
}


def check_vocab(items, report):
    seen_locations = set()
    seen_crops = set()
    for i in items:
        ct = i.get("contentType")
        if ct and ct not in CONTENT_TYPES:
            report.error("vocab: {} has an unrecognized contentType '{}'".format(i.get("id"), ct))
        for t in i.get("topics") or []:
            if t not in TOPICS:
                report.error("vocab: {} has an unrecognized topic '{}'".format(i.get("id"), t))
        seen_locations.update(i.get("locations") or [])
        seen_crops.update(i.get("croppingSystems") or [])

    # Locations/cropping systems are an open vocabulary by design (see schema comments),
    # so near-duplicates are a warning, not a failure, catches "US" vs "USA" style drift.
    _warn_near_duplicates(seen_locations, "locations", report)
    _warn_near_duplicates(seen_crops, "croppingSystems", report)


def _warn_near_duplicates(values, label, report):
    normalized = {}
    for v in values:
        key = re.sub(r"[^a-z0-9]", "", v.lower())
        normalized.setdefault(key, []).append(v)
    for key, variants in normalized.items():
        if len(variants) > 1:
            report.warn("vocab: {} has near-duplicate values that may need merging: {}".format(label, variants))


def check_no_secrets(data, report):
    blob = json.dumps(data)
    for pattern in SECRET_PATTERNS:
        if pattern.search(blob):
            report.error("privacy: the export contains something that looks like a credential/secret, refusing to describe it further, go check the source data")
            break

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.strip().lower() in INTERNAL_ONLY_KEYS:
                    report.error("privacy: internal-only field '{}' found at {} -- this must not be in the public export".format(k, path or "(root)"))
                walk(v, path + "/" + k)
        elif isinstance(obj, list):
            for idx, v in enumerate(obj):
                walk(v, "{}[{}]".format(path, idx))

    walk(data)


def check_against_previous(items, report, previous_path):
    if not previous_path or not os.path.exists(previous_path):
        report.warn("history: no previous snapshot given/found, skipping the 'existing records preserved' check")
        return
    with open(previous_path) as f:
        prev = json.load(f)
    prev_ids = {i["id"] for i in prev.get("items", []) if i.get("id")}
    cur_ids = {i["id"] for i in items if i.get("id")}

    removed = prev_ids - cur_ids
    added = cur_ids - prev_ids
    if removed:
        report.warn(
            "history: {} id(s) present in {} are missing from this export: {}"
            .format(len(removed), os.path.basename(previous_path), sorted(removed)[:20])
        )
    if added:
        report.warn("history: {} new id(s) since the previous snapshot: {}".format(len(added), sorted(added)[:20]))


def find_previous_snapshot(current_path):
    data_dir = os.path.dirname(current_path)
    candidates = sorted(glob.glob(os.path.join(data_dir, "database-*.json")))
    candidates = [c for c in candidates if os.path.abspath(c) != os.path.abspath(current_path)]
    return candidates[-1] if candidates else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_DATA, help="database.json to validate")
    ap.add_argument("--previous", default=None, help="a prior snapshot to diff against")
    args = ap.parse_args()

    report = Report()
    data = load_json(args.file, report, "file")
    if data is None:
        print_report(report, args.file)
        sys.exit(1)

    check_schema(data, report)
    items = check_structure(data, report)
    check_ids(items, report)
    check_required_fields(items, report)
    check_dates(items, report)
    check_urls(items, report)
    check_vocab(items, report)
    check_no_secrets(data, report)

    previous_path = args.previous or find_previous_snapshot(os.path.abspath(args.file))
    check_against_previous(items, report, previous_path)

    print_report(report, args.file)
    sys.exit(0 if report.ok() else 1)


def print_report(report, filename):
    print("Validating {}".format(filename))
    print("-" * 60)
    if report.errors:
        print("FAILED -- {} error(s):".format(len(report.errors)))
        for e in report.errors:
            print("  [ERROR] " + e)
    else:
        print("No errors.")
    if report.warnings:
        print("{} warning(s) (not blocking):".format(len(report.warnings)))
        for w in report.warnings:
            print("  [warn] " + w)
    print("-" * 60)
    print("RESULT: {}".format("SAFE TO PUBLISH" if report.ok() else "DO NOT PUBLISH -- fix the errors above first"))


if __name__ == "__main__":
    main()
