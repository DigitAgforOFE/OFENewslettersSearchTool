(function(){
  "use strict";

  // Same-origin by default: app/ and data/ are siblings in the same GitHub Pages
  // site, so this is a normal same-origin fetch, not a cross-origin one, no CORS
  // configuration needed. Change this only if database.json is ever hosted
  // somewhere else (see the CORS note in README.md).
  var DATA_URL = "../data/database.json";

  var FACETS = [
    {key:"contentType",     label:"Content type",      kind:"single"},
    {key:"topics",          label:"Topic",             kind:"multi"},
    {key:"locations",       label:"Location",          kind:"multi", searchable:true},
    {key:"croppingSystems", label:"Cropping system",   kind:"multi", searchable:true}
  ];

  var state = {
    q: "",
    qTerms: [],
    qWords: [],
    filters: { contentType: new Set(), topics: new Set(), locations: new Set(), croppingSystems: new Set() },
    dateFrom: "",
    dateTo: "",
    showExpired: false
  };

  var allItems = [];
  var facetCounts = {};

  fetch(DATA_URL, {cache:"no-store"})
    .then(function(r){
      if(!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function(data){
      allItems = data.items || [];
      buildFacetOptions();
      renderFacets();
      render();
      var gen = data.generatedAt ? new Date(data.generatedAt) : null;
      document.getElementById("footer").innerHTML =
        "Library last updated " + (gen ? gen.toLocaleDateString(undefined,{year:"numeric",month:"long",day:"numeric"}) : "recently") +
        " · " + (data.count || allItems.length) + " resources · Curated from the ISPA OFE Community (OFE-C) newsletter archive.";
    })
    .catch(function(err){
      document.getElementById("cards").innerHTML =
        '<div class="empty-state">Could not load the resource library right now (' + escapeHtml(err.message) + '). Please try again shortly.</div>';
    });

  function buildFacetOptions(){
    FACETS.forEach(function(f){
      var counts = {};
      allItems.forEach(function(it){
        var v = it[f.key];
        var vals = Array.isArray(v) ? v : (v ? [v] : []);
        vals.forEach(function(x){ counts[x] = (counts[x]||0) + 1; });
      });
      facetCounts[f.key] = counts;
    });
  }

  function renderFacets(){
    var nav = document.getElementById("facets");
    nav.innerHTML = "";

    // Clear filters
    var clearWrap = document.createElement("div");
    var clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "clear-btn";
    clearBtn.textContent = "Clear all filters";
    clearBtn.addEventListener("click", function(){
      FACETS.forEach(function(f){ state.filters[f.key].clear(); });
      state.dateFrom = ""; state.dateTo = "";
      document.getElementById("q").value = "";
      state.q = "";
      state.qTerms = [];
      state.qWords = [];
      renderFacets();
      render();
    });
    clearWrap.appendChild(clearBtn);
    nav.appendChild(clearWrap);

    // Date range facet
    var dateDet = document.createElement("details");
    dateDet.className = "facet";
    var dateSum = document.createElement("summary");
    dateSum.innerHTML = "<span>Date</span><span class='arrow'>▸</span>";
    dateDet.appendChild(dateSum);
    var dateBody = document.createElement("div");
    dateBody.className = "facet-body date-range";
    dateBody.innerHTML =
      '<label>From<input type="date" id="dateFrom"></label>' +
      '<label>To<input type="date" id="dateTo"></label>';
    dateDet.appendChild(dateBody);
    nav.appendChild(dateDet);

    FACETS.forEach(function(f){
      var det = document.createElement("details");
      det.className = "facet";
      det.open = (f.key === "contentType");
      var sum = document.createElement("summary");
      sum.innerHTML = "<span>" + f.label + (state.filters[f.key].size ? " (" + state.filters[f.key].size + ")" : "") + "</span><span class='arrow'>▸</span>";
      det.appendChild(sum);

      var body = document.createElement("div");
      body.className = "facet-body";

      var options = Object.keys(facetCounts[f.key]).sort(function(a,b){
        return facetCounts[f.key][b] - facetCounts[f.key][a] || a.localeCompare(b);
      });

      var optionsWrap = document.createElement("div");
      optionsWrap.className = "facet-options";

      function renderOptions(filterText){
        optionsWrap.innerHTML = "";
        options.forEach(function(opt){
          if (filterText && opt.toLowerCase().indexOf(filterText.toLowerCase()) === -1) return;
          var label = document.createElement("label");
          var input = document.createElement("input");
          input.type = "checkbox";
          input.checked = state.filters[f.key].has(opt);
          input.addEventListener("change", function(){
            if (input.checked) state.filters[f.key].add(opt); else state.filters[f.key].delete(opt);
            renderFacets();
            render();
          });
          label.appendChild(input);
          var span = document.createElement("span");
          span.textContent = opt;
          label.appendChild(span);
          var n = document.createElement("span");
          n.className = "n";
          n.textContent = facetCounts[f.key][opt];
          label.appendChild(n);
          optionsWrap.appendChild(label);
        });
      }

      if (f.searchable){
        var searchInput = document.createElement("input");
        searchInput.type = "search";
        searchInput.className = "facet-search";
        searchInput.placeholder = "Filter " + f.label.toLowerCase() + "…";
        searchInput.addEventListener("input", function(){ renderOptions(searchInput.value); });
        body.appendChild(searchInput);
      }

      renderOptions("");
      body.appendChild(optionsWrap);
      det.appendChild(body);
      nav.appendChild(det);
    });

    var dateFromEl = document.getElementById("dateFrom");
    var dateToEl = document.getElementById("dateTo");
    dateFromEl.value = state.dateFrom;
    dateToEl.value = state.dateTo;
    dateFromEl.addEventListener("change", function(){ state.dateFrom = dateFromEl.value; render(); });
    dateToEl.addEventListener("change", function(){ state.dateTo = dateToEl.value; render(); });

    // Show past listings toggle — low-priority, tucked at the bottom of the panel
    var toggleWrap = document.createElement("div");
    toggleWrap.className = "facet-footer";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "expired-toggle" + (state.showExpired ? " active" : "");
    btn.textContent = (state.showExpired ? "☑" : "☐") + " Show past job postings & surveys";
    btn.addEventListener("click", function(){
      state.showExpired = !state.showExpired;
      renderFacets();
      render();
    });
    toggleWrap.appendChild(btn);
    nav.appendChild(toggleWrap);

    renderActiveChips();
  }

  function renderActiveChips(){
    var wrap = document.getElementById("activeChips");
    wrap.innerHTML = "";
    FACETS.forEach(function(f){
      state.filters[f.key].forEach(function(val){
        var chip = document.createElement("span");
        chip.className = "active-chip";
        chip.textContent = val;
        var b = document.createElement("button");
        b.type = "button";
        b.setAttribute("aria-label", "Remove filter " + val);
        b.textContent = "✕";
        b.addEventListener("click", function(){
          state.filters[f.key].delete(val);
          renderFacets();
          render();
        });
        chip.appendChild(b);
        wrap.appendChild(chip);
      });
    });
    if (state.dateFrom || state.dateTo){
      var chip = document.createElement("span");
      chip.className = "active-chip";
      chip.textContent = (state.dateFrom || "…") + " → " + (state.dateTo || "…");
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-label", "Clear date range");
      b.textContent = "✕";
      b.addEventListener("click", function(){
        state.dateFrom = ""; state.dateTo = "";
        renderFacets();
        render();
      });
      chip.appendChild(b);
      wrap.appendChild(chip);
    }
  }

  // Facets, date range, and the expired-listings toggle: a hard AND applied
  // on top of search ranking no matter which method (keyword, semantic, or
  // both merged) produced the ranking. Unrelated to text relevance.
  function passesFilters(item){
    if (!state.showExpired && item.expired) return false;

    for (var i=0;i<FACETS.length;i++){
      var f = FACETS[i];
      var chosen = state.filters[f.key];
      if (chosen.size === 0) continue;
      var v = item[f.key];
      var vals = Array.isArray(v) ? v : (v ? [v] : []);
      var any = false;
      for (var j=0;j<vals.length;j++){ if (chosen.has(vals[j])) { any = true; break; } }
      if (!any) return false;
    }

    if (state.dateFrom && (!item.publishDate || item.publishDate < state.dateFrom)) return false;
    if (state.dateTo && (!item.publishDate || item.publishDate > state.dateTo)) return false;

    return true;
  }

  // Every query word must appear as a prefix of some word, anywhere in the
  // item. This is the strict keyword layer; semantic ranking (see
  // semantic.js) doesn't require this and can surface items that fail it.
  function passesKeyword(item){
    if (!state.qTerms || !state.qTerms.length) return true;
    var hay = (
      (item.title || "") + " " +
      (item.summary || "") + " " +
      (item.topics||[]).join(" ") + " " +
      (item.contentType || "") + " " +
      (item.locations||[]).join(" ") + " " +
      (item.croppingSystems||[]).join(" ") + " " +
      (item.people||[]).join(" ") + " " +
      (item.pageKeywords||[]).join(" ")
    );
    hay = foldAccents(hay).toLowerCase();
    for (var t=0;t<state.qTerms.length;t++){
      if (!state.qTerms[t].test(hay)) return false;
    }
    return true;
  }

  function escapeRegExp(s){
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  // Strips accents/diacritics (e.g. "Gésan-Guiziou" -> "Gesan-Guiziou") so a
  // search for the unaccented form still matches names/terms that carry one —
  // most people won't type "é" on purpose.
  function foldAccents(s){
    return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  // Only these can follow a query term for it to still count as a match —
  // common inflections, not an arbitrary tail. This is what lets "trial"
  // match "trials" and "tool" match "tools" without also letting "corn"
  // match "cornell" (an unrelated word that simply happens to start with
  // the same four letters — plain prefix matching got this wrong).
  var SUFFIXES = ["'s","es","ers","er","ing","ed","s","d"];
  var SUFFIX_PATTERN = "(?:" + SUFFIXES.join("|") + ")?";

  // Multi-word queries are AND'd — every word must match (exactly, or with
  // one of the suffixes above) some word anywhere in the item, not
  // necessarily as a contiguous phrase.
  function buildQueryTerms(q){
    q = foldAccents(q);
    return q.split(/\s+/).filter(Boolean).map(function(term){
      return new RegExp("\\b" + escapeRegExp(term) + SUFFIX_PATTERN + "\\b");
    });
  }

  // Same suffix rule as buildQueryTerms, applied to a single already-folded
  // word for highlighting (see highlightText below).
  function wordMatchesTerm(word, term){
    if (word.length < term.length || word.indexOf(term) !== 0) return false;
    var suffix = word.slice(term.length);
    return suffix === "" || SUFFIXES.indexOf(suffix) !== -1;
  }

  // Relevance score for a query-active list: title hits outrank a hit in
  // contentType/topics, which outranks a hit anywhere else (summary, people,
  // locations, croppingSystems, pageKeywords). Used to sort results instead
  // of leaving them in newsletter order once someone has typed a query.
  function scoreItem(item, qTerms){
    if (!qTerms || !qTerms.length) return 0;
    var titleHay = foldAccents(item.title || "").toLowerCase();
    var midHay = foldAccents((item.contentType || "") + " " + (item.topics||[]).join(" ")).toLowerCase();
    var lowHay = foldAccents(
      (item.summary || "") + " " +
      (item.people||[]).join(" ") + " " +
      (item.locations||[]).join(" ") + " " +
      (item.croppingSystems||[]).join(" ") + " " +
      (item.pageKeywords||[]).join(" ")
    ).toLowerCase();

    var score = 0;
    qTerms.forEach(function(re){
      if (re.test(titleHay)) score += 3;
      else if (re.test(midHay)) score += 2;
      else if (re.test(lowHay)) score += 1;
    });
    return score;
  }

  var WORD_RE = /[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*/g;

  // Wraps words in `text` that start with any of the active query terms in
  // <mark>, so a card visibly shows why it matched. Escapes everything else,
  // so this is safe to drop straight into innerHTML.
  function highlightText(text, qWords){
    text = String(text == null ? "" : text);
    if (!qWords || !qWords.length) return escapeHtml(text);

    var out = "", last = 0, m;
    WORD_RE.lastIndex = 0;
    while ((m = WORD_RE.exec(text))){
      out += escapeHtml(text.slice(last, m.index));
      var word = m[0];
      var folded = foldAccents(word).toLowerCase();
      var isMatch = qWords.some(function(w){ return wordMatchesTerm(folded, w); });
      out += isMatch ? "<mark>" + escapeHtml(word) + "</mark>" : escapeHtml(word);
      last = m.index + word.length;
    }
    out += escapeHtml(text.slice(last));
    return out;
  }

  // Same word-match rule as highlightText, but just a yes/no — used to tell
  // whether a piece of text (a topic, a chip label) is worth prioritizing
  // or highlighting at all, without building the marked-up HTML for it.
  function textHasQueryMatch(text, qWords){
    if (!qWords || !qWords.length) return false;
    var words = String(text||"").match(WORD_RE) || [];
    return words.some(function(w){
      var folded = foldAccents(w).toLowerCase();
      return qWords.some(function(q){ return wordMatchesTerm(folded, q); });
    });
  }

  // Which of `values` (locations, croppingSystems, people, pageKeywords —
  // fields that matched by the keyword search but never render on the
  // card) actually contain a query term. Used to explain a match that
  // would otherwise be invisible, without dumping the whole (often noisy,
  // scraped) field onto the card.
  function matchingValues(qTerms, values){
    if (!qTerms || !qTerms.length || !values || !values.length) return [];
    return values.filter(function(v){
      var hay = foldAccents(v).toLowerCase();
      return qTerms.some(function(re){ return re.test(hay); });
    });
  }

  function escapeHtml(s){
    return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }

  function dedupePreserveOrder(arr){
    var seen = {}, out = [];
    arr.forEach(function(x){
      var k = x.toLowerCase();
      if (!seen[k]){ seen[k] = true; out.push(x); }
    });
    return out;
  }

  function doiUrl(doi){
    return "https://doi.org/" + doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
  }

  // A handful of newsletter items ("Recent papers on OFE" and the like) bundle
  // several papers' citations into one record instead of one paper each. Detect
  // that generically from the doi/publication fields (semicolon-separated lists
  // that match up 1:1) rather than special-casing specific item ids, so any
  // future digest entered the same way in Notion is picked up automatically.
  function citedPapers(item){
    var dois = dedupePreserveOrder((item.doi || "").split(";").map(function(s){ return s.trim(); }).filter(Boolean));
    var pubs = (item.publication || "").split(";").map(function(s){ return s.trim(); }).filter(Boolean);
    if (dois.length < 2 || dois.length !== pubs.length) return null;
    return dois.map(function(d, i){ return { citation: pubs[i], url: doiUrl(d), doi: d }; });
  }

  function cardHtml(item, semanticOnly){
    var papers = citedPapers(item);
    // If the raw summary is just those same citations run together with no
    // spacing (the common case for these digests), swap it for the clean list.
    var summaryIsCitationDump = !!papers && papers.some(function(p){ return (item.summary||"").indexOf(p.doi) !== -1; });

    var citationsHtml = "";
    if (papers){
      citationsHtml =
        '<div class="citations-label">' + papers.length + ' papers cited</div>' +
        '<div class="citations">' + papers.map(function(p){
          return '<div class="citation"><a href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener">' + highlightText(p.citation, state.qWords) + '</a></div>';
        }).join("") + '</div>';
    }

    var linkBit;
    if (item.url && !summaryIsCitationDump){
      var badge = item.urlStatus === "archived"
        ? ' <span class="badge archived">Archived copy</span>'
        : "";
      linkBit = '<div class="learn"><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">View resource →</a>' + badge + '</div>';
    } else if (!item.url) {
      linkBit = '<div class="no-link">No link available</div>';
    } else {
      linkBit = "";
    }

    var hasQuery = !!(state.qWords && state.qWords.length);

    // Matched topics float to the front of the (still capped-at-4) list, so
    // a topic that's why this card is here doesn't get bumped off by ones
    // that aren't, and gets highlighted the same way title/summary text does.
    var topicsToShow = (item.topics||[]).slice();
    if (hasQuery){
      topicsToShow.sort(function(a,b){
        return textHasQueryMatch(b, state.qWords) - textHasQueryMatch(a, state.qWords);
      });
    }
    topicsToShow = topicsToShow.slice(0,4);

    var chips = "";
    if (semanticOnly){
      chips += '<span class="chip semantic" title="No matching words, but related in meaning to your search">✦ Related by meaning</span>';
    }
    if (item.contentType) chips += '<span class="chip type">' + highlightText(item.contentType, state.qWords) + '</span>';
    topicsToShow.forEach(function(t){ chips += '<span class="chip">' + highlightText(t, state.qWords) + '</span>'; });

    // If this matched by keyword search but nothing rendered above actually
    // shows a highlighted word (the match lives in a field the card doesn't
    // display — pageKeywords, people, locations, croppingSystems), say so
    // explicitly rather than leaving the card looking unrelated. Only the
    // values that actually matched are shown, not the whole field.
    if (hasQuery && !semanticOnly){
      var hasVisibleMatch =
        textHasQueryMatch(item.title, state.qWords) ||
        textHasQueryMatch(item.summary, state.qWords) ||
        textHasQueryMatch(item.contentType, state.qWords) ||
        topicsToShow.some(function(t){ return textHasQueryMatch(t, state.qWords); }) ||
        (papers && papers.some(function(p){ return textHasQueryMatch(p.citation, state.qWords); }));

      if (!hasVisibleMatch){
        var hiddenMatches = dedupePreserveOrder(
          matchingValues(state.qTerms, item.pageKeywords)
            .concat(matchingValues(state.qTerms, item.people))
            .concat(matchingValues(state.qTerms, item.locations))
            .concat(matchingValues(state.qTerms, item.croppingSystems))
        ).slice(0,4);
        if (hiddenMatches.length){
          chips += '<span class="chip hint" title="Found in this item\'s tags or the page it links to, not shown elsewhere on this card">Also matches: ' + escapeHtml(hiddenMatches.join(", ")) + '</span>';
        }
      }
    }

    var dateStr = "";
    if (item.publishDate){
      var d = new Date(item.publishDate);
      if (!isNaN(d)) dateStr = d.toLocaleDateString(undefined,{year:"numeric",month:"short"});
    }

    var bodyHtml = summaryIsCitationDump
      ? citationsHtml
      : ('<div class="summary">' + highlightText(item.summary||"", state.qWords) + '</div>' + citationsHtml);

    var titleText = highlightText(item.title, state.qWords);
    var hasResourceLink = !!(item.url && !summaryIsCitationDump);
    var titleHtml = hasResourceLink
      ? '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + titleText + '</a>'
      : titleText;

    return (
      '<article class="card">' +
        '<h3>' + titleHtml + '</h3>' +
        '<div class="meta">' + [dateStr, item.sourceNewsletter].filter(Boolean).join(" · ") + '</div>' +
        bodyHtml +
        '<div class="chips">' + chips + '</div>' +
        linkBit +
      '</article>'
    );
  }

  var renderTimer = null;
  function scheduleRender(){
    clearTimeout(renderTimer);
    renderTimer = setTimeout(render, 300);
  }

  var RRF_K = 60;

  // A flat "top 50 by similarity" was showing up nearly the whole library
  // for almost every query: this corpus is all on-farm-experimentation
  // content, so even loosely-related items score moderately on cosine
  // similarity, there's no fixed score that means "irrelevant" across every
  // query. What's consistent is the *shape* of a good match: relevant
  // results cluster near the top score, then similarity falls off. So we
  // keep only results within 15% of the best match for this query (and
  // require that best match to clear an absolute floor first, so a query
  // with nothing genuinely related — the floor is calibrated against
  // corpus-wide "nonsense query" testing — returns nothing rather than
  // its closest-by-default neighbors).
  var SEMANTIC_RELATIVE_RATIO = 0.85;
  var SEMANTIC_MIN_SCORE = 0.30;
  var SEMANTIC_MAX_RESULTS = 30; // safety cap, not the normal cutoff

  function filterSemanticResults(scored){
    if (!scored.length) return [];
    var threshold = Math.max(scored[0].score * SEMANTIC_RELATIVE_RATIO, SEMANTIC_MIN_SCORE);
    var kept = [];
    for (var i=0; i<scored.length && kept.length<SEMANTIC_MAX_RESULTS; i++){
      if (scored[i].score < threshold) break; // scored is sorted desc already
      kept.push(scored[i].item);
    }
    return kept;
  }

  // Reciprocal Rank Fusion: an item ranking well in both lists floats to the
  // top; an item only one method found still shows up, just lower. Ranks
  // are 1-based positions within each already-sorted list.
  function mergeRRF(keywordRanked, semanticRanked){
    var scores = new Map();
    var byId = new Map();
    keywordRanked.forEach(function(item, i){
      byId.set(item.id, item);
      scores.set(item.id, (scores.get(item.id)||0) + 1/(RRF_K + i + 1));
    });
    semanticRanked.forEach(function(item, i){
      byId.set(item.id, item);
      scores.set(item.id, (scores.get(item.id)||0) + 1/(RRF_K + i + 1));
    });
    var merged = Array.from(byId.values());
    merged.sort(function(a,b){ return scores.get(b.id) - scores.get(a.id); });
    return merged;
  }

  function render(){
    var base = allItems.filter(passesFilters);
    var hasQuery = state.qWords && state.qWords.length > 0;
    var ranked;
    var keywordMatchIds = null; // null = don't know/don't care (no query, or keyword-only mode)

    if (!hasQuery){
      ranked = base;
    } else {
      var keywordRanked = base.filter(passesKeyword);
      keywordRanked.sort(function(a,b){ return scoreItem(b, state.qTerms) - scoreItem(a, state.qTerms); });

      if (window.SemanticSearch && window.SemanticSearch.isReady()){
        var semanticRanked = filterSemanticResults(window.SemanticSearch.rankItems(state.q, base));
        ranked = keywordRanked.length ? mergeRRF(keywordRanked, semanticRanked) : semanticRanked;
        // Only meaningful once semantic ranking is actually in play: cards
        // with no shared words (nothing for highlightText to bold) get a
        // "Related by meaning" badge instead, so it's clear why they're here.
        keywordMatchIds = new Set(keywordRanked.map(function(item){ return item.id; }));
      } else {
        ranked = keywordRanked;
      }
    }

    var cardsEl = document.getElementById("cards");
    var emptyEl = document.getElementById("emptyState");
    document.getElementById("countPill").textContent = ranked.length + " of " + allItems.length + " resources";

    if (ranked.length === 0){
      cardsEl.innerHTML = "";
      emptyEl.hidden = false;
    } else {
      emptyEl.hidden = true;
      cardsEl.innerHTML = ranked.map(function(item){
        var semanticOnly = !!keywordMatchIds && !keywordMatchIds.has(item.id);
        return cardHtml(item, semanticOnly);
      }).join("");
    }
  }

  var qInput = document.getElementById("q");

  qInput.addEventListener("input", function(e){
    state.q = e.target.value.trim().toLowerCase();
    state.qTerms = buildQueryTerms(state.q);
    state.qWords = foldAccents(state.q).split(/\s+/).filter(Boolean);
    scheduleRender();
  });

  // Lazy-load the semantic model only once someone actually focuses the
  // search box, so the base page (browsing/filtering, no typing) stays
  // fast. Re-render when it finishes in case a query is already active.
  qInput.addEventListener("focus", function(){
    if (!window.SemanticSearch) return;
    window.SemanticSearch.init().then(render).catch(function(err){
      console.warn("Semantic search unavailable:", err.message);
    });
  }, { once: true });

})();
