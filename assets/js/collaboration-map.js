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
      Number.isFinite(Number(d.longitude))
    );
  }

  function locationLabel(d) {
    return [d.city, d.region, d.country].filter(Boolean).join(", ");
  }

  function renderDetails(d) {
    if (!detailsEl || !d) return;

    const coauthors = (d.coauthors || []).map(escapeHtml).join(", ");
    const papers = (d.papers || []).slice(0, 8).map(p => {
      const title = p.url
        ? `<a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>`
        : escapeHtml(p.title);
      const names = (p.coauthors || []).map(escapeHtml).join(", ");
      return `<li>${title}${p.year ? ` (${escapeHtml(p.year)})` : ""}${names ? `<br><span>${names}</span>` : ""}</li>`;
    }).join("");

    detailsEl.innerHTML = `
      <h3>${escapeHtml(d.name)}</h3>
      <p class="collaboration-map-meta">
        ${escapeHtml(locationLabel(d))}
        ${locationLabel(d) && d.paper_count ? " · " : ""}
        ${d.paper_count ? paperCountLabel(Number(d.paper_count)) : ""}
      </p>
      ${coauthors ? `<p><strong>Co-authors:</strong> ${coauthors}</p>` : ""}
      ${papers ? `<ul class="collaboration-paper-list">${papers}</ul>` : ""}
    `;
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

    const maxPapers = Math.max(1, d3.max(institutions, d => Number(d.paper_count || 1)));
    const radius = d3.scaleSqrt().domain([1, maxPapers]).range([4.5, 10]);

    const nodes = svg.append("g")
      .attr("class", "collaboration-map-nodes")
      .selectAll("circle")
      .data(institutions)
      .join("circle")
      .attr("class", "collaboration-map-node")
      .attr("cx", d => projection([Number(d.longitude), Number(d.latitude)])[0])
      .attr("cy", d => projection([Number(d.longitude), Number(d.latitude)])[1])
      .attr("r", d => radius(Number(d.paper_count || 1)))
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("aria-label", d => `${d.name}. ${locationLabel(d)}. ${paperCountLabel(Number(d.paper_count || 0))}.`)
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
        nodes.classed("is-selected", false);
        d3.select(this).classed("is-selected", true);
        renderDetails(d);
      });

    nodes.append("title")
      .text(d => `${d.name} — ${locationLabel(d)} — ${paperCountLabel(Number(d.paper_count || 0))}`);

    const mappedPaperIds = new Set();
    institutions.forEach(inst => (inst.papers || []).forEach(p => mappedPaperIds.add(p.id || p.title)));

    if (statusEl) {
      statusEl.textContent =
        `${institutionCountLabel(institutions.length)} · ` +
        `${paperCountLabel(mappedPaperIds.size)} with resolved co-author affiliations`;
    }

    const first = institutions
      .slice()
      .sort((a, b) =>
        Number(b.paper_count || 0) - Number(a.paper_count || 0) ||
        String(a.name).localeCompare(String(b.name))
      )[0];

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