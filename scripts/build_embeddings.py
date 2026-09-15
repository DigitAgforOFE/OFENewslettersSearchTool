#!/usr/bin/env python3
"""
OFE Newsletters Search Tool — semantic search embeddings builder
=================================================================

WHAT THIS IS
------------
Run this right after data/database.json is (re)generated, as the last step
of the monthly pipeline. It produces the two things the browser's semantic
search layer needs, and nothing else changes about how the site is built or
served (still static files, no backend):

1. data/embeddings.json
   One 128-dim vector per item (encoded from title + summary), used to rank
   items by meaning at search time. Small (a few hundred KB).

2. data/model2vec/  (vocab.txt, embeddings.int8.bin, scales.bin, model.json)
   The token embedding table the *browser* uses to embed whatever the user
   types into the search box. This is the ~4 MB one-time download per
   visitor mentioned in the search design doc. It is int8-quantized
   (one scale factor per token row, so per-token precision doesn't get
   crushed by a few high-magnitude outlier tokens) to keep that download
   small. It is fetched lazily by app/semantic.js, only once someone
   focuses the search box, so pages that are just being browsed/filtered
   never pay for it.

WHY POTION-BASE-4M, NOT POTION-BASE-8M
---------------------------------------
The search design doc names potion-base-8M "or similar." 8M's 256-dim
vectors quantize to ~7.5 MB (29,528 vocab tokens x 256 dims x 1 byte),
noticeably more than the "~4 MB" figure the doc cites (that figure traces
to a blog post using a smaller/similarly-sized static model). potion-base-4M
uses the same tokenizer and vocab but 128-dim vectors, quantizing to ~3.8 MB
— a close match to that target. Side-by-side tests against this project's
own 275 items (see the "measuring outcomes beyond yield" example in the
design doc, which is meant to surface "Measuring More Than Yield") showed
comparable ranking quality between 4M and 8M at this corpus size, so there
is no real accuracy cost for the smaller download. If the corpus grows a
lot and semantic quality needs a boost later, swapping MODEL_NAME below to
"minishlab/potion-base-8M" is the whole change needed on the Python side —
app/semantic.js reads dim/vocab size from model.json, it doesn't hardcode
128.

NO JS ML LIBRARY NEEDED
------------------------
There is no browser-side "model2vec.js" package to load from a CDN. A
model2vec model is just a token lookup table + mean pooling, so
app/semantic.js hand-rolls the ~150 lines of tokenization + lookup itself
(WordPiece tokenizer matching this model's bert-base-style vocab, then
mean-pool + L2-normalize). This avoids needing app/vendor/ or a CDN
dependency at all for this piece.

SETUP
-----
    pip install model2vec

USAGE
-----
    python3 scripts/build_embeddings.py
    python3 scripts/build_embeddings.py --database data/database.json

Re-run this any time data/database.json changes. It always rewrites
data/embeddings.json and data/model2vec/ from scratch (the model files
themselves only change if MODEL_NAME below changes, but they're cheap to
regenerate so this doesn't try to skip that).
"""

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATABASE = os.path.join(ROOT, "data", "database.json")
EMBEDDINGS_JSON = os.path.join(ROOT, "data", "embeddings.json")
MODEL_DIR = os.path.join(ROOT, "data", "model2vec")

MODEL_NAME = "minishlab/potion-base-4M"


def item_text(item):
    title = (item.get("title") or "").strip()
    summary = (item.get("summary") or "").strip()
    return (title + ". " + summary).strip(". ").strip()


def build_item_embeddings(model, items):
    texts = [item_text(it) for it in items]
    vectors = model.encode(texts)
    out_items = []
    for item, vec in zip(items, vectors):
        out_items.append({"id": item["id"], "vector": [round(float(x), 6) for x in vec]})
    return out_items


def build_browser_model_assets(model):
    """Export the token embedding table the browser needs to embed a query.

    Row-wise (per-token) int8 quantization: each of the 29,528 token rows
    gets its own scale = max(abs(row)) / 127, so a handful of unusually
    large tokens can't blow out the resolution for everything else. This
    matters here because mean-pooling happens *before* normalization on the
    JS side (matching model2vec's own encode()), so per-token scale error
    directly affects which tokens dominate a short query's pooled vector.
    """
    embedding = np.asarray(model.embedding, dtype=np.float32)  # (vocab, dim)
    vocab_size, dim = embedding.shape

    scales = np.abs(embedding).max(axis=1) / 127.0
    scales = np.where(scales == 0, 1.0, scales)  # avoid div-by-zero for any all-zero row
    quantized = np.round(embedding / scales[:, None]).clip(-127, 127).astype(np.int8)

    os.makedirs(MODEL_DIR, exist_ok=True)

    with open(os.path.join(MODEL_DIR, "embeddings.int8.bin"), "wb") as f:
        f.write(quantized.tobytes())

    with open(os.path.join(MODEL_DIR, "scales.bin"), "wb") as f:
        f.write(scales.astype(np.float32).tobytes())

    # vocab.txt: one token per line, line number == token id (must match the
    # embedding row order exactly — this is how model2vec/BERT vocab files
    # already work, so we just pass the tokenizer's own vocab through).
    id_to_token = [None] * vocab_size
    vocab_dict = model.tokenizer.get_vocab()
    for token, idx in vocab_dict.items():
        id_to_token[idx] = token
    if any(t is None for t in id_to_token):
        missing = [i for i, t in enumerate(id_to_token) if t is None]
        raise SystemExit(f"vocab export incomplete, missing ids: {missing[:10]}...")

    with open(os.path.join(MODEL_DIR, "vocab.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(id_to_token))

    model_config = {
        "model": MODEL_NAME,
        "dim": int(dim),
        "vocabSize": int(vocab_size),
        "unkToken": "[UNK]",
        "unkId": int(vocab_dict["[UNK]"]),
        "continuingSubwordPrefix": "##",
        "maxInputCharsPerWord": 100,
        "doLowerCase": True,
        "stripAccents": True,
    }
    with open(os.path.join(MODEL_DIR, "model.json"), "w", encoding="utf-8") as f:
        json.dump(model_config, f, indent=2)

    return vocab_size, dim


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    args = parser.parse_args()

    try:
        from model2vec import StaticModel
    except ImportError:
        sys.exit("model2vec is not installed. Run: pip install model2vec")

    with open(args.database, encoding="utf-8") as f:
        db = json.load(f)
    items = db.get("items", [])
    if not items:
        sys.exit(f"No items found in {args.database}")

    print(f"Loading {MODEL_NAME}...")
    model = StaticModel.from_pretrained(MODEL_NAME)

    print(f"Encoding {len(items)} items...")
    out_items = build_item_embeddings(model, items)
    with open(EMBEDDINGS_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "model": MODEL_NAME,
            "dim": len(out_items[0]["vector"]) if out_items else 0,
            "items": out_items,
        }, f)
    print(f"Wrote {EMBEDDINGS_JSON} ({len(out_items)} vectors)")

    print("Exporting browser query-encoder assets...")
    vocab_size, dim = build_browser_model_assets(model)
    print(f"Wrote {MODEL_DIR}/ (vocab={vocab_size}, dim={dim})")

    ids_db = {it["id"] for it in items}
    ids_emb = {it["id"] for it in out_items}
    if ids_db != ids_emb:
        sys.exit(f"Mismatch between database ids and embedding ids: {ids_db.symmetric_difference(ids_emb)}")

    print("Done.")


if __name__ == "__main__":
    main()
