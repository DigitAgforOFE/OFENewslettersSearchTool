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

  function matches(item){
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

    if (state.qTerms && state.qTerms.length){
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

  // Whole-word terms: "corn" must not match "cornell", and vice versa.
  // Multi-word queries are AND'd — every word must appear, each as its own
  // whole word, anywhere in the item (not necessarily as a contiguous phrase).
  function buildQueryTerms(q){
    q = foldAccents(q);
    return q.split(/\s+/).filter(Boolean).map(function(term){
      return new RegExp("\\b" + escapeRegExp(term) + "\\b");
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

  function cardHtml(item){
    var papers = citedPapers(item);
    // If the raw summary is just those same citations run together with no
    // spacing (the common case for these digests), swap it for the clean list.
    var summaryIsCitationDump = !!papers && papers.some(function(p){ return (item.summary||"").indexOf(p.doi) !== -1; });

    var citationsHtml = "";
    if (papers){
      citationsHtml =
        '<div class="citations-label">' + papers.length + ' papers cited</div>' +
        '<div class="citations">' + papers.map(function(p){
          return '<div class="citation"><a href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener">' + escapeHtml(p.citation) + '</a></div>';
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

    var chips = "";
    if (item.contentType) chips += '<span class="chip type">' + escapeHtml(item.contentType) + '</span>';
    (item.topics||[]).slice(0,4).forEach(function(t){ chips += '<span class="chip">' + escapeHtml(t) + '</span>'; });

    var dateStr = "";
    if (item.publishDate){
      var d = new Date(item.publishDate);
      if (!isNaN(d)) dateStr = d.toLocaleDateString(undefined,{year:"numeric",month:"short"});
    }

    var bodyHtml = summaryIsCitationDump
      ? citationsHtml
      : ('<div class="summary">' + escapeHtml(item.summary||"") + '</div>' + citationsHtml);

    return (
      '<article class="card">' +
        '<h3>' + escapeHtml(item.title) + '</h3>' +
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

  function render(){
    var filtered = allItems.filter(matches);
    var cardsEl = document.getElementById("cards");
    var emptyEl = document.getElementById("emptyState");
    document.getElementById("countPill").textContent = filtered.length + " of " + allItems.length + " resources";

    if (filtered.length === 0){
      cardsEl.innerHTML = "";
      emptyEl.hidden = false;
    } else {
      emptyEl.hidden = true;
      cardsEl.innerHTML = filtered.map(cardHtml).join("");
    }
  }

  document.getElementById("q").addEventListener("input", function(e){
    state.q = e.target.value.trim().toLowerCase();
    state.qTerms = buildQueryTerms(state.q);
    scheduleRender();
  });

})();
