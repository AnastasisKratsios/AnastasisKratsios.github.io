(function () {
  "use strict";

  const DATA_URL = "data/collaborations.json";
  const WORLD_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

  const svgEl = document.getElementById("collaboration-map-canvas");
  const detailsEl = document.getElementById("collaboration-map-details");
  const statusEl = document.getElementById("collaboration-map-status");

  if (!svgEl) return;

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;"
    }[c]));
  }

  function paperCountLabel(n) {
    return `${n} ${n === 1 ? "paper" : "papers"}`;
  }

  function institutionCountLabel(n) {
    return `${n} ${n === 1 ? "institution" : "institutions"}`;
  }

  function validInstitutions(data) {
    return (data.institutions || []).filter(d =>
      d &&
      Number.isFinite(Number(d.latitude)) &&
      Number.isFinite(Number(d.longitude)) &&
      (d.has_historical || d.has_current || Number(d.paper_count || 0) > 0)
    );
  }

  function locationLabel(d) {
    return [d.city, d.region, d.country].filter(Boolean).join(", ");
  }

  function ensureLegend() {
    if (!statusEl || document.getElementById("collaboration-map-legend")) return;
    const legend = document.createElement("div");
    legend.id = "collaboration-map-legend";
    legend.className = "collaboration-map-legend";
    legend.innerHTML = `
      <span><i class="collaboration-legend-dot"></i> institution on a joint paper</span>
      <span><i class="collaboration-legend-ring"></i> current co-author affiliation</span>
    `;
    statusEl.insertAdjacentElement("afterend", legend);
  }

  function sourceLink(source) {
    if (!source || !source.source_url) return "";
    const label = source.source_type ? escapeHtml(source.source_type) : "source";
    return ` <a href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener">[${label}]</a>`;
  }

  function renderDetails(d) {
    if (!detailsEl || !d) return;

    const historicalNames = (d.coauthors || []).map(escapeHtml).join(", ");
    const currentNames = (d.current_coauthors || []).map(escapeHtml).join(", ");

    const papers = (d.papers || []).slice(0, 12).map(p => {
      const title = p.url
        ? `<a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>`
        : escapeHtml(p.title);
      const names = (p.coauthors || []).map(escapeHtml).join(", ");
      return `<li>${title}${p.year ? ` (${escapeHtml(p.year)})` : ""}${names ? `<br><span>${names}</span>` : ""}</li>`;
    }).join("");

    const currentEvidence = (d.current_sources || []).map(source => {
      const person = escapeHtml(source.person || "");
      const note = source.note ? ` — ${escapeHtml(source.note)}` : "";
      return `<li>${person}${sourceLink(source)}${note}</li>`;
    }).join("");

    detailsEl.innerHTML = `
      <h3>${escapeHtml(d.name)}</h3>
      <p class="collaboration-map-meta">
        ${escapeHtml(locationLabel(d))}
        ${locationLabel(d) && d.paper_count ? " · " : ""}
        ${d.paper_count ? paperCountLabel(Number(d.paper_count)) : ""}
      </p>

      ${d.has_historical ? `
        <div class="collaboration-detail-section">
          <h4>On joint publications</h4>
          ${historicalNames ? `<p><strong>Co-authors:</strong> ${historicalNames}</p>` : ""}
          ${papers ? `<ul class="collaboration-paper-list">${papers}</ul>` : ""}
        </div>
      ` : ""}

      ${d.has_current ? `
        <div class="collaboration-detail-section collaboration-current-detail">
          <h4>Current affiliation</h4>
          ${currentNames ? `<p><strong>Co-authors currently here:</strong> ${currentNames}</p>` : ""}
          ${currentEvidence ? `<ul class="collaboration-current-source-list">${currentEvidence}</ul>` : ""}
        </div>
      ` : ""}
    `;
  }

  function makeDisplayPoints(institutions, projection) {
    // Separate institutions that share a city/coordinate (Toronto, Oxford, Zürich, etc.)
    // by a tiny deterministic screen-space offset so every node remains clickable.
    const grouped = new Map();

    institutions.forEach(d => {
      const raw = projection([Number(d.longitude), Number(d.latitude)]);
      if (!raw) return;
      const key = `${Number(d.latitude).toFixed(3)}:${Number(d.longitude).toFixed(3)}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push({d, raw});
    });

    const positions = new Map();
    grouped.forEach(items => {
      items.sort((a, b) => String(a.d.name).localeCompare(String(b.d.name)));
      const n = items.length;

      items.forEach((item, i) => {
        if (n === 1) {
          positions.set(item.d, item.raw);
          return;
        }

        const angle = (2 * Math.PI * i / n) - Math.PI / 2;
        const spread = n <= 2 ? 6 : n <= 4 ? 8 : 10;
        positions.set(item.d, [
          item.raw[0] + spread * Math.cos(angle),
          item.raw[1] + spread * Math.sin(angle)
        ]);
      });
    });

    return positions;
  }

  function renderMap(world, data) {
    const d3 = window.d3;
    const topojson = window.topojson;
    const institutions = validInstitutions(data);

    if (!institutions.length) {
      if (statusEl) statusEl.textContent = "No geocoded co-author institutions are available yet.";
      if (detailsEl) detailsEl.innerHTML = "<p>The map will populate after the collaboration updater runs successfully.</p>";
      return;
    }

    const width = 1000;
    const height = 520;
    const svg = d3.select(svgEl)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("preserveAspectRatio", "xMidYMid meet");

    svg.selectAll("*").remove();

    const countries = topojson.feature(world, world.objects.countries);
    const projection = d3.geoNaturalEarth1()
      .fitExtent([[20, 18], [width - 20, height - 18]], countries);
    const path = d3.geoPath(projection);

    svg.append("path")
      .datum({type: "Sphere"})
      .attr("class", "collaboration-map-sphere")
      .attr("d", path);

    svg.append("g")
      .attr("aria-hidden", "true")
      .selectAll("path")
      .data(countries.features)
      .join("path")
      .attr("class", "collaboration-map-country")
      .attr("d", path);

    const maxPapers = Math.max(1, d3.max(institutions, d => Number(d.paper_count || 0)));
    const radius = d3.scaleSqrt().domain([1, maxPapers]).range([4.2, 9.5]);
    const positions = makeDisplayPoints(institutions, projection);

    const groups = svg.append("g")
      .attr("class", "collaboration-map-nodes")
      .selectAll("g")
      .data(institutions)
      .join("g")
      .attr("class", d => [
        "collaboration-map-node-group",
        d.has_historical ? "has-historical" : "",
        d.has_current ? "has-current" : ""
      ].filter(Boolean).join(" "))
      .attr("transform", d => {
        const p = positions.get(d) || projection([Number(d.longitude), Number(d.latitude)]);
        return `translate(${p[0]},${p[1]})`;
      })
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("aria-label", d => {
        const parts = [d.name, locationLabel(d)];
        if (d.has_historical) parts.push(paperCountLabel(Number(d.paper_count || 0)));
        if (d.has_current) parts.push("current co-author affiliation");
        return parts.filter(Boolean).join(". ");
      })
      .on("mouseenter", function (event, d) {
        d3.select(this).classed("is-active", true);
        renderDetails(d);
      })
      .on("mouseleave", function () {
        d3.select(this).classed("is-active", false);
      })
      .on("focus", function (event, d) {
        d3.select(this).classed("is-active", true);
        renderDetails(d);
      })
      .on("blur", function () {
        d3.select(this).classed("is-active", false);
      })
      .on("click", function (event, d) {
        groups.classed("is-selected", false);
        d3.select(this).classed("is-selected", true);
        renderDetails(d);
      });

    groups.filter(d => d.has_current)
      .append("circle")
      .attr("class", "collaboration-map-current-ring")
      .attr("r", d => Math.max(7.5, radius(Math.max(1, Number(d.paper_count || 1))) + 3.2));

    groups.filter(d => d.has_historical)
      .append("circle")
      .attr("class", "collaboration-map-historical-dot")
      .attr("r", d => radius(Math.max(1, Number(d.paper_count || 1))));

    groups.filter(d => !d.has_historical && d.has_current)
      .append("circle")
      .attr("class", "collaboration-map-current-only-core")
      .attr("r", 2.2);

    groups.append("circle")
      .attr("class", "collaboration-map-hit")
      .attr("r", d => Math.max(12, radius(Math.max(1, Number(d.paper_count || 1))) + 5));

    groups.append("title")
      .text(d => {
        const bits = [`${d.name} — ${locationLabel(d)}`];
        if (d.has_historical) bits.push(paperCountLabel(Number(d.paper_count || 0)));
        if (d.has_current) bits.push("current affiliation");
        return bits.join(" — ");
      });

    const mappedPaperIds = new Set();
    institutions.forEach(inst => (inst.papers || []).forEach(p => mappedPaperIds.add(p.id || p.title)));
    const historicalCount = institutions.filter(d => d.has_historical).length;
    const currentCount = institutions.filter(d => d.has_current).length;

    if (statusEl) {
      statusEl.textContent =
        `${institutionCountLabel(historicalCount)} on joint papers · ` +
        `${institutionCountLabel(currentCount)} with current co-author affiliations · ` +
        `${paperCountLabel(mappedPaperIds.size)} resolved`;
    }

    ensureLegend();

    const first = institutions
      .filter(d => d.has_historical)
      .slice()
      .sort((a, b) =>
        Number(b.paper_count || 0) - Number(a.paper_count || 0) ||
        String(a.name).localeCompare(String(b.name))
      )[0] || institutions[0];

    renderDetails(first);
  }

  async function init() {
    if (!window.d3 || !window.topojson) {
      if (statusEl) statusEl.textContent = "Map libraries did not load.";
      return;
    }

    try {
      const [data, world] = await Promise.all([
        fetch(DATA_URL, {cache: "no-store"}).then(r => {
          if (!r.ok) throw new Error(`Could not load ${DATA_URL}`);
          return r.json();
        }),
        window.d3.json(WORLD_URL)
      ]);
      renderMap(world, data);
    } catch (error) {
      console.error("Collaboration map:", error);
      if (statusEl) statusEl.textContent = "The collaboration map could not be loaded.";
      if (detailsEl) detailsEl.innerHTML = "<p>Collaboration data will reappear after the next successful update.</p>";
    }
  }

  init();
})();