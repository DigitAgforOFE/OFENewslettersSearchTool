# OFE Newsletters Search Tool — publishing runbook

This is the standalone web app and dataset behind the OFE Newsletters
Search Tool: a searchable, taggable library of resources drawn from
On-Farm Experimentation (OFE) newsletters. Right now the sole source is
the newsletter published by the International Society of Precision
Agriculture's OFE Community (ISPA OFE-C); other sources (for example the
GOFEN website, or others) may be added later without changing this
architecture. It's built to the architecture in the build brief: a
static, client-side search app fed by a JSON file, hosted on GitHub
Pages, embeddable into any site that can host an iframe or embed block
(currently planned: Louis's Google Site).

Files move between here and GitHub through VS Code (clone once, then
edit → commit → sync), not through GitHub's browser upload page, see
"Get the files onto GitHub, using VS Code" below.

```
Notion (source of truth, 275 curated items)
        │  monthly export (Claude does this for you)
        ▼
data/database.json  ──┐
app/index.html         │
app/search.js          ├──  pushed to GitHub  ──  GitHub Pages  ──  embedded wherever it's needed
app/search.css         │
schema, scripts, docs ─┘
```

## Folder layout

```
OFENewslettersSearchTool/
├── data/
│   ├── database.json          the live dataset the app reads
│   ├── database-2026-09.json  a dated snapshot, kept permanently
│   ├── embeddings.json        per-item semantic search vectors (see "Semantic search" below)
│   └── model2vec/             browser query-encoder assets: vocab.txt, embeddings.int8.bin, scales.bin, model.json
├── schema/
│   └── database.schema.json   formal schema + controlled vocabularies
├── app/
│   ├── index.html             page structure
│   ├── search.js              fetch, keyword search + ranking, filters, rendering
│   ├── semantic.js            browser-side semantic search (tokenize, embed, rank)
│   └── search.css             styling
├── scripts/
│   ├── export_notion_to_json.py     standalone Notion -> JSON export (reference/fallback)
│   ├── validate_data.py             validates database.json before anything gets published
│   ├── build_embeddings.py          generates data/embeddings.json and data/model2vec/ (see "Semantic search")
│   ├── enrich_search_keywords.py    generates pageKeywords (see "Search enrichment" below)
│   ├── check_page_keywords.py       consistency checks for pageKeywords, run before publishing
│   ├── enrichment_report.json       current pageKeywords coverage + what's left unenriched and why
│   ├── enrichment_changelog.json    per-item diff from the last enrichment pass
│   └── manual_keyword_review.md     items the script couldn't reach on its own, triaged
├── processing-log.json        one line per export: counts + what changed
└── README.md                  this file
```

This matches the layout in the build brief. `app/index.html` works
standalone, opening it directly (via its GitHub Pages URL) shows the full
library; Google Sites just embeds that same URL.

## Why this is a separate app instead of a Squarespace/Google-Sites-native page

Neither Squarespace's Basic plan nor Google Sites can run a real search
application natively, they're page builders, not app hosts. Splitting the
app onto its own static host (GitHub Pages) and embedding it is exactly
the brief's design principle: *"a small static web application with a
JSON data layer, embedded in Google Sites"* rather than a search engine
built inside the site editor. That also means this same app can later be
dropped into a GOFEN page, another Google Site, gofen.org, or anywhere
else, without rebuilding anything, since the tool itself isn't tied to
any one destination site or content source.

## One-time setup

### 1. Create a GitHub account (skip if you already have one)

Free, at [github.com/signup](https://github.com/signup).

### 2. Create a new repository

- Click the **+** in the top right → **New repository**.
- Name it `OFENewslettersSearchTool` (or anything you like).
- Set it to **Public** (required for free GitHub Pages).
- Leave it otherwise empty, don't add a README/gitignore, we already have one.
- Click **Create repository**.

### 3. Get the files onto GitHub, using VS Code

This project uses VS Code (instead of GitHub's browser upload page) to
move files back and forth. It's a one-time setup, after that, publishing
a change is a few clicks in a sidebar, and you get to see exactly what
changed before it goes live, which drag-and-drop upload never showed you.

**Install VS Code and Git**

- Download VS Code free at [code.visualstudio.com](https://code.visualstudio.com)
  and install it like any other Mac app.
- You also need Git. If it isn't already on your Mac, the first time VS
  Code needs it (the clone step below) it will offer to install it for
  you, just click through that, no Terminal typing required.

**Clone the repo**

- Open VS Code.
- Press **Cmd+Shift+P** to open the Command Palette, type `Git: Clone`,
  press Enter.
- Paste the repo URL: `https://github.com/DigitAgforOFE/OFENewslettersSearchTool.git`
- When asked where to save it, pick the `NewslettersSearchTool` folder
  (see the note just below first, since a plain `OFENewslettersSearchTool`
  folder already lives there).
- Click **Open** when VS Code asks if you want to open the cloned repo.
- The first time, VS Code opens a browser window asking you to sign in to
  GitHub and authorize VS Code, sign in there, no token or password to
  type anywhere in VS Code itself.

**Bring the existing files into the clone**

The `OFENewslettersSearchTool` folder in `NewslettersSearchTool` already
has every project file, it just isn't tracked by Git yet. Simplest way to
combine the two:

1. In Finder, rename the existing `OFENewslettersSearchTool` folder to
   `OFENewslettersSearchTool-files` (right-click → Rename).
2. Do the clone step above, this creates a fresh, empty
   `OFENewslettersSearchTool` folder that's linked to GitHub.
3. Copy everything out of `OFENewslettersSearchTool-files` into the new
   `OFENewslettersSearchTool` folder.
4. In VS Code, **File → Open Folder** → select the new
   `OFENewslettersSearchTool`. Open the Source Control panel (the
   branching-line icon in the left sidebar, or **Cmd+Shift+G**), every
   file appears under "Changes."
5. Click the **+** next to "Changes" to stage everything, type a commit
   message like `Initial publish` in the box at the top, click the
   checkmark to commit.
6. Click **Sync Changes** (or **Publish Branch**, whichever shows) to
   push everything to GitHub.
7. Once the files show up on github.com and the app still works, delete
   the `OFENewslettersSearchTool-files` backup folder.

**A heads-up about OneDrive:** this project folder lives inside your
OneDrive sync. That's fine for the project files themselves, but OneDrive
and Git both watching the same folder can occasionally make OneDrive flag
Git's internal `.git` files as "conflicts." That never affects your
actual project files, any `.git`-conflict copies OneDrive creates are
safe to ignore or delete. If it gets annoying, the fix is moving this
folder to a plain, non-synced location like `~/Documents/GitHub/`,
just say so and Claude can help, though Claude would then need that new
folder connected to keep writing the monthly exports directly into it.

### 4. Turn on GitHub Pages

- In the repo, go to **Settings → Pages**.
- Source: **Deploy from a branch**. Branch: **main**, folder: **/ (root)**. Save.
- GitHub gives you a URL like `https://<your-username>.github.io/OFENewslettersSearchTool/`.
  Takes a minute or two to go live the first time.

### 5. Check the app works on its own

Open `https://<your-username>.github.io/OFENewslettersSearchTool/app/` (note
the `/app/` at the end, that's where `index.html` lives). You should see
the full library: search, filters, cards, all 275 resources. Try a search
and a filter before moving to the embed step, this is the brief's "prove
it works standalone before embedding" checkpoint.

### 6. Embed it in the Google Site

In the Google Site editor:

1. Click **Insert**.
2. Choose **Embed**.
3. Paste the app's URL: `https://<your-username>.github.io/OFENewslettersSearchTool/app/`
4. Click **Insert**, then **Publish** to save the change.

Google's own help notes that a small number of sites block being embedded
this way; GitHub Pages doesn't, so this should just work. If the embed
shows a blank box instead of the library, that's the thing to check first,
try the standalone URL from step 5 directly in a browser tab to confirm
the app itself is fine, then re-check the embed.

### 7. Resize if needed

Google Sites gives embedded content a fixed height by default; if the
library gets cut off, drag the embed's resize handle in the site editor
taller, or set a generous fixed height (900px or more comfortably fits the
filters + several rows of results on most screens).

## Monthly publish checklist

1. Process the new newsletter in a Claude session as usual (extract items,
   tag them, review anything flagged).
2. Confirm the new rows are in the Notion database and look right.
3. Say to Claude: **"run the monthly OFE Newsletters Search Tool
   export."** Claude queries Notion directly, regenerates `data/database.json`
   (writing straight into your cloned `OFENewslettersSearchTool` folder), runs
   `validate_data.py` against it, and only if that passes writes the new
   dated snapshot and updates `processing-log.json`. You get a short
   change report back: which items were added, removed, or edited since
   last month.
4. Run the search enrichment on the newsletter's new items so they're
   searchable by page content too, not just their own summary (see
   "Search enrichment" below for what this does and why):
   ```
   python3 scripts/enrich_search_keywords.py
   python3 scripts/check_page_keywords.py
   ```
   New items are exactly what this picks up, since it only processes
   items that don't already have `pageKeywords`, everything from prior
   months is untouched. Check `scripts/manual_keyword_review.md` for
   anything it couldn't reach on its own.
5. Regenerate the semantic search vectors so new items are findable by
   meaning, not just keyword (see "Semantic search" below):
   ```
   pip install model2vec
   python3 scripts/build_embeddings.py
   ```
   Re-run `validate_data.py` (next step) after this — it checks that
   `data/embeddings.json` has a vector for every item in `database.json`
   and will fail the build if this step gets skipped.
6. In VS Code, open the Source Control panel (**Cmd+Shift+G**). You'll
   see `data/database.json`, the new `data/database-YYYY-MM.json`
   snapshot, `data/embeddings.json`, `processing-log.json`, and the
   `scripts/enrichment_*` files listed under "Changes." Click any file
   name to see a colored diff of exactly what changed before you commit
   anything. Stage the files (the **+** next to each, or next to
   "Changes" to stage all), type a commit message like `Monthly update —
   September 2026`, commit (✓), then click **Sync Changes** to push to
   GitHub.
7. Reload the GitHub Pages app URL and spot-check: new items show up,
   search and filters still work.

Nothing on the Google Site itself needs editing for a normal monthly
update, only `data/database.json` changes, which is the whole point of
keeping the app and the data separate.

## Search enrichment (`pageKeywords`)

Each item's own text (title, summary, tags) is what search matches by
default, but the linked page it points to often contains useful terms
the newsletter blurb never mentions, an author's name, a specific
technique, a place. `pageKeywords` closes that gap: it's a per-item list
of terms scraped or looked up from the linked page, filtered to exclude
anything already covered by the item's own title/summary/tags, and
included in `search.js`'s search match. It's search-only, it never
appears on the card UI.

**Generating it** — `scripts/enrich_search_keywords.py` visits each
item's `url` and extracts terms from the page text. For sites that block
scraping (paywalled publishers, Cloudflare) it falls back to free
scholarly metadata (OpenAlex/Crossref, keyed by the item's `doi`) or, for
YouTube links, the oEmbed API, both of which sidestep the block entirely
rather than trying to defeat it. Re-running it only processes items that
don't already have `pageKeywords`, so it's safe to run again each month:

```
pip install requests beautifulsoup4 pypdf
python3 scripts/enrich_search_keywords.py
```

Add `--force` to re-fetch specific items (`--only OFE-010,OFE-057`) if a
page's content has changed or a link got fixed. See the top of the
script for the full option list.

**What it can't reach on its own** ends up in
`scripts/manual_keyword_review.md`, split into items not worth chasing
(dead links, video/file-only pages, login walls, nothing to gain even for
a human) and items with real content behind a block worth a manual
visit, at which point the workflow is: open the link yourself, paste
whatever loads back into a Claude session, and it extracts and files the
keywords the same way the script would have.

**Before publishing any pageKeywords change**, run the consistency
checker, it catches things schema validation won't (duplicate keywords,
a keyword that just duplicates the item's own summary text, a
`pageKeywordsSource` value that doesn't match its counterpart fields,
malformed DOIs, leftover tracking/wrapper URLs):

```
python3 scripts/check_page_keywords.py
```

## Semantic search

Keyword search (the `pageKeywords`-enriched match described above) is
exact-word matching with a title/topic-priority ranking, it's very good at
proper nouns (tool names, people, acronyms like GARDIAN) but blind to
paraphrasing: searching "measuring outcomes beyond yield" won't find an
item titled "Measuring More Than Yield" unless the words happen to
overlap. Semantic search closes that gap by ranking items by *meaning*
instead of shared words, and the two are merged (Reciprocal Rank Fusion)
so a query that matches well on both ranks highest, a query that only one
method finds still surfaces, and a query with zero keyword matches falls
back to semantic-only ranking rather than an empty results page.

**How it works, no backend required.** `scripts/build_embeddings.py` uses
[model2vec](https://github.com/MinishLab/model2vec) (`potion-base-4M`,
chosen so its quantized vocabulary table lands close to the ~4 MB budget
in the search design doc) to precompute a 128-dim vector for every item's
title + summary, written to `data/embeddings.json`. It also exports that
model's own token-embedding table, quantized to ~3.8 MB, to
`data/model2vec/`. `app/semantic.js` is a ~200-line hand-rolled
tokenizer + lookup (there's no browser-side "model2vec.js" package worth
pulling in — a model2vec model is just "tokenize, look up each token's
vector, average, normalize," so this reimplements that directly against
the exported table). It fetches those files and embeds whatever's typed
into the search box entirely client-side: no API key, no per-query cost,
nothing to run except a static-file fetch.

**It's lazy-loaded.** Nothing under `data/model2vec/` or
`data/embeddings.json` is fetched until someone focuses the search box,
so anyone who's just browsing/filtering the library never pays for the
~4 MB download. It's cached by the browser after that first fetch.

**Regenerating it.** Run this any time `data/database.json` changes
(step 5 of the monthly checklist above does this):
```
pip install model2vec
python3 scripts/build_embeddings.py
```
`validate_data.py` checks that `data/embeddings.json` covers every id in
`database.json` (and no stale ones), so a forgotten regeneration fails
validation instead of silently shipping a search index that's out of sync
with the data.

## If the app itself ever needs a change

Editing `search.js`, `search.css`, or `index.html` (new filter, a design
tweak, a bug fix) is separate from the monthly data update, and rarer.
Same process: edit the file in VS Code, save it, optionally preview it
locally first (see below), then use the Source Control panel to stage,
commit, and **Sync Changes**, exactly like a monthly data update. The
Google Site embed doesn't need to change at all, it just points at the
URL, whatever's currently published there is what visitors see.

## Previewing the app locally before pushing

Double-clicking `app/index.html` and opening it straight from Finder
won't work, the app fetches `data/database.json` with JavaScript, and
browsers block that kind of request from a plain `file://` page. You need
a local server first:

**Easiest: VS Code's Live Server extension**

1. In VS Code, click the Extensions icon in the left sidebar (four
   squares), search for **Live Server** (by Ritwick Dey), click Install.
2. Right-click `app/index.html` in the file list and choose **Open with
   Live Server**.
3. Your browser opens the app running locally, at something like
   `http://127.0.0.1:5500/app/`. Edits you save in VS Code reload the
   page automatically.

**Alternative: a one-line local server**, if you'd rather not install an
extension. Open VS Code's built-in terminal (**Terminal → New
Terminal**), from the `OFENewslettersSearchTool` folder run:

```
python3 -m http.server 8000
```

then open `http://localhost:8000/app/` in a browser. Press Control+C in
the terminal to stop the server when you're done.

## Design decisions worth knowing

- **Public fields only.** `Curator notes` and `Duplicate status` stay
  internal to Notion and are never exported.
- **Dead links are resolved before publishing.** Each item's link is the
  original if it's live, or the working replacement if it isn't (Wayback
  Machine copies are labeled "Archived copy"). A handful of items with no
  working substitute show "No link available" rather than a broken link.
- **Job postings and surveys hide automatically once stale** (publish
  date + 90 days, there's rarely an explicit deadline in the newsletter
  text to key off more precisely). They're not deleted, a "Show past
  job postings & surveys" toggle in the filters brings them back.
- **Topic/Location/Cropping-system filters use OR logic** within each
  facet and AND logic between facets, per the brief.
- **`people` is unreviewed, auto-extracted data.** It's a real field in
  the JSON and it is searched, but expect noise (partial names, org-name
  fragments picked up by a keyword pass, not a curated directory). Worth a
  cleanup pass in Notion at some point; not blocking for launch.
- **`pageKeywords` is search-only.** It never renders on a card, it only
  widens what a search term can match. It's absent (not an empty array)
  on items the enrichment script couldn't get anything useful from, see
  `scripts/manual_keyword_review.md` for why on any specific item.
- **Search folds accents.** "Gésan-Guiziou" matches a search for
  "gesan-guiziou" too, most people won't type the accent on purpose, and
  several `pageKeywords` entries carry one (author/place names scraped
  verbatim from a source page).
- **Why there's no separate merge/dedup engine in the export script:**
  the brief's NEW/UPDATE/DUPLICATE/UNCERTAIN classification already
  happens each month when items get added to Notion, that's what "extract
  → tag → check for duplicates → push to Notion" already is. The export
  step just snapshots Notion's current, already-merged state, and
  `validate_data.py` plus the change report (added/removed/updated ids)
  give you the audit trail the brief asks for, without duplicating logic
  that Notion already handles.

## CORS and caching, and why they're a non-issue here

The brief flags CORS as something to test explicitly (section 19). In
this layout it's moot: `app/index.html` fetches `../data/database.json`
from the *same* GitHub Pages origin, that's a same-origin request, not a
cross-origin one, so there's no CORS configuration to get right. (Google
Sites embedding the app via an iframe doesn't create a CORS issue either,
the fetch happens inside the iframe's own origin, not the parent page's.)
This only becomes a real concern if `database.json` is ever moved to a
different host than the app itself; if that ever happens, the fix is
adding CORS headers on whichever host serves the JSON, and updating
`DATA_URL` near the top of `search.js`.

Caching: the app fetches `database.json` once per page load with
`cache: "no-store"`, so a visitor always gets the current file, no manual
cache-busting needed after a monthly update.

## Validation, and what "do not publish" means in practice

`scripts/validate_data.py` checks: valid JSON, schema conformance,
required fields present, unique IDs, sane dates, http(s) URLs, controlled
vocabulary for Content Type and Topic (Location and Cropping system are
intentionally open vocabularies, it warns on likely near-duplicates like
"US" vs "USA" instead of failing), no internal-only fields leaking into
the public export, and that the declared `count` matches the actual item
count. It also diffs against the previous snapshot and reports what
changed.

When Claude runs the monthly export, this validation runs automatically;
if it fails, `data/database.json` is left untouched and the previous,
already-published version stays live, nothing broken ever reaches GitHub
Pages. You can also run it by hand any time:

```
pip install jsonschema
python3 scripts/validate_data.py
```

## Troubleshooting

- **Google Site shows a blank box where the library should be:** open the
  GitHub Pages `/app/` URL directly in a new tab first, if that works
  fine, the issue is the embed step (re-check the URL you pasted); if it
  doesn't, the issue is upstream (see the next two points).
- **App loads but shows no resources / an error message:** almost always
  means `data/database.json` didn't upload, or `app/index.html` and
  `data/` aren't siblings anymore (don't move `app/index.html` without
  also updating the relative path in `search.js`).
- **New month's items aren't showing up:** confirm step 4 of the monthly
  checklist actually completed and GitHub Pages finished rebuilding (can
  take a minute after a commit).
- **A specific link goes nowhere:** check that item in Notion, the
  `Replacement URL` field may need a manual fix; the next export picks it
  up automatically.
- **`validate_data.py` fails:** read its error list, it names the exact
  item and field. Fix it in Notion and re-run the export.
- **Source Control panel shows no changes even though a file was edited
  or Claude regenerated the data:** make sure VS Code has the cloned
  `OFENewslettersSearchTool` folder open (**File → Open Folder**), not a
  different copy or its parent folder.
- **Sync Changes / Publish Branch fails or asks you to sign in again:**
  normal after the first setup or if your GitHub session expired, just
  sign back in when prompted.
- **OneDrive shows a "conflict" file inside the project folder:**
  almost always about Git's internal `.git` files, not your actual
  project files, safe to ignore or delete. See the OneDrive note in the
  setup section above if it keeps happening.
