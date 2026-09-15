# Manual keyword review — resolved

This tracked the punch-list of items `scripts/enrich_search_keywords.py`
couldn't enrich on its own. **That list is now resolved.** 223 of 242
items with a URL have `pageKeywords`; the 19 that don't fall into two
buckets, neither of which needs further action:

## Not worth visiting (16) — nothing to gain

Dead job postings/surveys, video/file links with no page text, LinkedIn/
whiteboard/dashboard apps: OFE-004, 048, 052, 087, 088, 093, 098, 107,
116, 175, 178, 209, 218, 226, 244, 280. (Reasons for each are in
scripts/enrichment_changelog.json's predecessor discussion; unchanged
since the original triage.)

## Confirmed dead end (3) — checked, nothing recoverable

- **OFE-181 / OFE-199** — the Wiley special-section call-for-papers page
  is gone; not in the Wayback Machine (the one snapshot that exists
  predates these items and is for a different special issue); a
  Crossref/OpenAlex title search for the special issue itself turned up
  nothing. Nothing beyond what's already in the item's own summary
  (special issue title, editor, deadline) is recoverable.
- **OFE-187** — its two cited papers' OpenAlex/Crossref metadata offers
  nothing beyond what the item's own summary already quotes verbatim
  (both paper titles are pasted directly into the summary as citations).

See `scripts/enrichment_changelog.json` for the full per-item diff of
everything that changed to get from the original 145 to the current 223.
