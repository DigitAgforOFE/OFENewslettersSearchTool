(function(){
  "use strict";

  // Semantic (meaning-based) search layer, described in the search design
  // doc. Loads nothing until init() is called (search.js calls it on the
  // first search-box focus), so browsing/filtering without typing a query
  // never pays for this.
  //
  // A model2vec model is a static token-lookup-and-average model: embed a
  // query by tokenizing it (WordPiece, same as BERT), looking up each
  // token's vector in a precomputed table, mean-pooling, and L2-normalizing.
  // There's no JS library for this worth pulling in over a CDN, it's short
  // enough to hand-roll here (matches minishlab/model2vec's own Python
  // encode(), see scripts/build_embeddings.py for how the table is built).

  var MODEL_BASE = "../data/model2vec/";
  var ITEM_EMBEDDINGS_URL = "../data/embeddings.json";

  var model = null;      // model.json contents
  var vocab = null;      // Map<token string, id>
  var int8 = null;       // Int8Array, vocabSize * dim
  var scales = null;     // Float32Array, one per token id
  var itemVectors = null; // Map<item id, Float32Array>

  var initPromise = null;
  var ready = false;

  function foldAccents(s){
    return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  // Matches BERT's BasicTokenizer punctuation set closely enough for the
  // short, plain-English queries this search box gets: ASCII punctuation
  // ranges plus the general Unicode punctuation category.
  function isPunctuation(ch){
    return /[!-/:-@[-`{-~]/.test(ch) || /\p{P}/u.test(ch);
  }

  function basicTokenize(text){
    text = foldAccents(text).toLowerCase();
    var words = text.split(/\s+/).filter(Boolean);
    var out = [];
    words.forEach(function(word){
      var cur = "";
      for (var i=0;i<word.length;i++){
        var ch = word[i];
        if (isPunctuation(ch)){
          if (cur){ out.push(cur); cur = ""; }
          out.push(ch);
        } else {
          cur += ch;
        }
      }
      if (cur) out.push(cur);
    });
    return out;
  }

  // Greedy longest-match WordPiece, same algorithm BERT/model2vec use.
  function wordpieceTokenize(word){
    if (word.length > model.maxInputCharsPerWord) return [model.unkId];
    var ids = [];
    var start = 0;
    while (start < word.length){
      var end = word.length;
      var curId = null;
      while (start < end){
        var substr = word.slice(start, end);
        if (start > 0) substr = model.continuingSubwordPrefix + substr;
        if (vocab.has(substr)){ curId = vocab.get(substr); break; }
        end -= 1;
      }
      if (curId === null) return [model.unkId];
      ids.push(curId);
      start = end;
    }
    return ids;
  }

  function tokenize(text){
    var words = basicTokenize(text);
    var ids = [];
    words.forEach(function(w){
      wordpieceTokenize(w).forEach(function(id){ ids.push(id); });
    });
    return ids;
  }

  function fetchBuffer(url){
    return fetch(url, {cache:"force-cache"}).then(function(r){
      if (!r.ok) throw new Error("HTTP " + r.status + " for " + url);
      return r.arrayBuffer();
    });
  }

  function fetchJson(url){
    return fetch(url, {cache:"force-cache"}).then(function(r){
      if (!r.ok) throw new Error("HTTP " + r.status + " for " + url);
      return r.json();
    });
  }

  function fetchText(url){
    return fetch(url, {cache:"force-cache"}).then(function(r){
      if (!r.ok) throw new Error("HTTP " + r.status + " for " + url);
      return r.text();
    });
  }

  function init(){
    if (initPromise) return initPromise;

    initPromise = Promise.all([
      fetchJson(MODEL_BASE + "model.json"),
      fetchText(MODEL_BASE + "vocab.txt"),
      fetchBuffer(MODEL_BASE + "embeddings.int8.bin"),
      fetchBuffer(MODEL_BASE + "scales.bin"),
      fetchJson(ITEM_EMBEDDINGS_URL)
    ]).then(function(results){
      model = results[0];
      var vocabLines = results[1].replace(/\r?\n$/, "").split(/\r?\n/);
      vocab = new Map();
      vocabLines.forEach(function(token, id){ vocab.set(token, id); });

      int8 = new Int8Array(results[2]);
      scales = new Float32Array(results[3]);

      var itemData = results[4];
      itemVectors = new Map();
      (itemData.items||[]).forEach(function(it){
        itemVectors.set(it.id, Float32Array.from(it.vector));
      });

      ready = true;
    });

    return initPromise;
  }

  function isReady(){ return ready; }

  // Embeds free text into the same space as the precomputed item vectors.
  // Returns null for empty/whitespace-only input (nothing to embed).
  function embedQuery(text){
    if (!ready) return null;
    var ids = tokenize(text);
    if (!ids.length) return null;

    var dim = model.dim;
    var sum = new Float64Array(dim);
    ids.forEach(function(id){
      var base = id * dim;
      var scale = scales[id];
      for (var d=0; d<dim; d++) sum[d] += int8[base+d] * scale;
    });

    var n = ids.length;
    var norm = 0;
    for (var d=0; d<dim; d++){ sum[d] /= n; norm += sum[d]*sum[d]; }
    norm = Math.sqrt(norm) + 1e-32;

    var out = new Float32Array(dim);
    for (var d=0; d<dim; d++) out[d] = sum[d] / norm;
    return out;
  }

  function vectorFor(itemId){
    return ready ? itemVectors.get(itemId) : undefined;
  }

  function cosineSim(a, b){
    var s = 0;
    for (var i=0;i<a.length;i++) s += a[i]*b[i];
    return s; // both sides are already unit-length, so dot product == cosine
  }

  // Ranks `items` (objects with an `id`) by similarity to `query`, most
  // similar first. Items with no precomputed vector, or a query that
  // tokenizes to nothing, are dropped. Returns [] rather than throwing if
  // the model isn't ready yet — callers should check isReady() first if
  // they need to distinguish "not ready" from "no semantic matches."
  function rankItems(query, items){
    var qv = embedQuery(query);
    if (!qv) return [];
    var scored = [];
    items.forEach(function(item){
      var iv = vectorFor(item.id);
      if (!iv) return;
      scored.push({ item: item, score: cosineSim(qv, iv) });
    });
    scored.sort(function(a,b){ return b.score - a.score; });
    return scored;
  }

  window.SemanticSearch = {
    init: init,
    isReady: isReady,
    embedQuery: embedQuery,
    rankItems: rankItems
  };

})();
