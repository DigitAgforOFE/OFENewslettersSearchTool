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

    // Show past listings toggle
    var toggleWrap = document.createElement("div");
    toggleWrap.className = "facet";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "expired-toggle";
    btn.textContent = "☐ Show past job postings & surveys";
    btn.addEventListener("click", function(){
      state.showExpired = !state.showExpired;
      btn.textContent = (state.showExpired ? "☑" : "☐") + " Show past job postings & surveys";
      btn.classList.toggle("active", state.showExpired);
      render();
    });
    toggleWrap.appendChild(btn);
    nav.appendChild(toggleWrap);

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

    if (state.q){
      var hay = (
        (item.title || "") + " " +
        (item.summary || "") + " " +
        (item.topics||[]).join(" ") + " " +
        (item.contentType || "") + " " +
        (item.locations||[]).join(" ") + " " +
        (item.croppingSystems||[]).join(" ") + " " +
        (item.people||[]).join(" ")
      ).toLowerCase();
      if (hay.indexOf(state.q) === -1) return false;
    }
    return true;
  }

  function escapeHtml(s){
    return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }

  function cardHtml(item){
    var linkBit;
    if (item.url){
      var badge = item.urlStatus === "archived"
        ? ' <span class="badge archived">Archived copy</span>'
        : "";
      linkBit = '<div class="learn"><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">View resource →</a>' + badge + '</div>';
    } else {
      linkBit = '<div class="no-link">No link available</div>';
    }

    var chips = "";
    if (item.contentType) chips += '<span class="chip type">' + escapeHtml(item.contentType) + '</span>';
    (item.topics||[]).slice(0,4).forEach(function(t){ chips += '<span class="chip">' + escapeHtml(t) + '</span>'; });

    var dateStr = "";
    if (item.publishDate){
      var d = new Date(item.publishDate);
      if (!isNaN(d)) dateStr = d.toLocaleDateString(undefined,{year:"numeric",month:"short"});
    }

    return (
      '<article class="card">' +
        '<h3>' + (item.url ? ('<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + escapeHtml(item.title) + '</a>') : escapeHtml(item.title)) + '</h3>' +
        '<div class="meta">' + [dateStr, item.sourceNewsletter].filter(Boolean).join(" · ") + '</div>' +
        '<div class="summary">' + escapeHtml((item.summary||"").slice(0,220)) + ((item.summary||"").length > 220 ? "…" : "") + '</div>' +
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
    scheduleRender();
  });

})();
