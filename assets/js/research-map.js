(function () {
  const SVG_ID = "research-map-canvas";
  const DATA_URL = "data/publications.json";
  const TOPIC_URL = "data/research_topics.json";

  const TOPIC_COLORS = {
    "AI Theory": "#2f4f9f",
    "Applications": "#91551f",
    "Approximation Theory": "#4768c5",
    "Statistical Learning Theory": "#5c72b8",
    "Reasoning & Computation": "#6a61a8",
    "Operator Learning": "#26839b",
    "Geometric Deep Learning": "#4c8f67",
    "PDEs": "#b06b2b",
    "Control & Optimization": "#b3822c",
    "Games & BSDEs": "#9f6b56",
    "Finance": "#b14e49",
    "Misc.": "#777777"
  };

  const state = {
    filter: "all",
    year: "all",
    search: "",
    publications: [],
    topics: null,
    selected: null
  };

  function byId(id) { return document.getElementById(id); }

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));
  }

  function normalize(str) {
    return String(str || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function paperMatches(p) {
    const q = normalize(state.search).trim();
    const text = normalize([p.title, p.authors, p.venue, (p.topics || []).join(" ")].join(" "));
    if (q && !text.includes(q)) return false;
    if (state.year !== "all" && String(p.year || "") !== String(state.year)) return false;
    if (state.filter === "all") return true;
    if (state.filter === "AI Theory") return (p.topics || []).some(t => ["Approximation Theory", "Statistical Learning Theory", "Reasoning & Computation", "Operator Learning", "Geometric Deep Learning"].includes(t));
    if (state.filter === "Applications") return (p.topics || []).some(t => ["PDEs", "Control & Optimization", "Games & BSDEs", "Finance", "Misc."].includes(t));
    return (p.topics || []).includes(state.filter) || p.primary_topic === state.filter;
  }

  function setStatus() {
    const el = byId("research-map-status");
    if (!el) return;
    const papers = state.publications.filter(paperMatches);
    const generated = state.generatedAt && state.generatedAt !== "seed" ? ` Last updated: ${state.generatedAt}.` : " Seed data shown until the first scheduled Scholar refresh succeeds.";
    el.textContent = `${papers.length} papers shown.${generated}`;
  }

  function populateControls() {
    const yearSelect = byId("research-map-year");
    if (yearSelect) {
      const years = Array.from(new Set(state.publications.map(p => p.year).filter(Boolean))).sort((a,b) => b-a);
      yearSelect.innerHTML = `<option value="all">All years</option>` + years.map(y => `<option value="${escapeHtml(y)}">${escapeHtml(y)}</option>`).join("");
      yearSelect.addEventListener("change", () => { state.year = yearSelect.value; render(); });
    }
    document.querySelectorAll("[data-research-filter]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.filter = btn.getAttribute("data-research-filter");
        document.querySelectorAll("[data-research-filter]").forEach(b => b.classList.toggle("is-active", b === btn));
        render();
      });
    });
    const search = byId("research-map-search");
    if (search) {
      search.addEventListener("input", () => { state.search = search.value || ""; render(); });
    }
  }

  function showPaper(p) {
    state.selected = p;
    const panel = byId("research-map-details");
    if (!panel) return;
    const topics = (p.topics || []).map(t => `<span class="research-topic-badge">${escapeHtml(t)}</span>`).join(" ");
    const link = p.url ? `<p><a class="paper-link" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">Open paper/source</a></p>` : "";
    const abstract = p.abstract ? `<p class="paper-abstract">${escapeHtml(p.abstract)}</p>` : `<p class="paper-abstract">No abstract was available in the cached metadata. The updater will fill this when Scholar/Semantic Scholar/OpenAlex returns it.</p>`;
    panel.innerHTML = `
      <h3>${escapeHtml(p.title)}</h3>
      <p class="paper-meta">${escapeHtml(p.authors || "")}<br>${escapeHtml([p.venue, p.year].filter(Boolean).join(" · "))}${p.citations ? ` · ${escapeHtml(p.citations)} citations` : ""}</p>
      <div>${topics}</div>
      ${abstract}
      ${link}
    `;
  }

  function showTopic(t, count) {
    const panel = byId("research-map-details");
    if (!panel) return;
    panel.innerHTML = `
      <h3>${escapeHtml(t.label || t.id)}</h3>
      <p class="paper-meta">${escapeHtml(t.root || "Root topic")} ${t.level ? `· level ${escapeHtml(t.level)}` : ""}</p>
      <p>${count} visible paper${count === 1 ? "" : "s"} currently attach to this topic.</p>
      <p>Use the tabs, year selector, and search box to isolate a research thread. The arrows encode the DAG-level organization; paper placement is updated from the cached publication metadata.</p>
    `;
  }

  function renderList() {
    const container = byId("publication-list");
    if (!container) return;
    const papers = state.publications.filter(paperMatches).sort((a,b) => (b.year || 0) - (a.year || 0) || String(a.title).localeCompare(String(b.title)));
    const grouped = new Map();
    papers.forEach(p => {
      const y = p.year || "Undated";
      if (!grouped.has(y)) grouped.set(y, []);
      grouped.get(y).push(p);
    });
    let html = `<h2>Publication list</h2>`;
    grouped.forEach((items, year) => {
      html += `<details ${String(year) === String(new Date().getFullYear()) ? "open" : ""}><summary>${escapeHtml(year)} · ${items.length} paper${items.length === 1 ? "" : "s"}</summary><ul>`;
      items.forEach(p => {
        const title = p.url ? `<a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>` : escapeHtml(p.title);
        html += `<li>${title}. <em>${escapeHtml(p.venue || "")}</em>${p.citations ? ` · ${escapeHtml(p.citations)} citations` : ""}<br><small>${(p.topics || []).map(escapeHtml).join(" · ")}</small></li>`;
      });
      html += `</ul></details>`;
    });
    container.innerHTML = html;
  }

  function nodeRadius(d) {
    if (d.kind === "root") return 25;
    if (d.kind === "topic") return 17;
    const c = Math.max(0, Number(d.citations || 0));
    return Math.max(5.5, Math.min(15, 5.5 + Math.sqrt(c + 1) * 1.4));
  }

  function render() {
    if (!window.d3) {
      const status = byId("research-map-status");
      if (status) status.textContent = "The graph library did not load, so the publication list below is shown instead.";
      renderList();
      return;
    }
    const svgEl = byId(SVG_ID);
    if (!svgEl || !state.topics) return;
    setStatus();
    renderList();

    const wrap = svgEl.parentElement;
    const width = Math.max(680, wrap ? wrap.clientWidth : 960);
    const height = Math.max(500, svgEl.clientHeight || 576);
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();

    const defs = svg.append("defs");
    defs.append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 22)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "rgba(0,0,0,0.35)");

    const visiblePapers = state.publications.filter(paperMatches);
    const topicNodes = state.topics.nodes.map(t => ({...t, fx: t.x * width, fy: t.y * height}));
    const topicMap = new Map(topicNodes.map(t => [t.id, t]));
    const topicCounts = new Map(topicNodes.map(t => [t.id, 0]));
    visiblePapers.forEach(p => (p.topics || []).forEach(t => topicCounts.set(t, (topicCounts.get(t) || 0) + 1)));

    const paperNodes = visiblePapers.map((p, i) => {
      const parent = topicMap.get(p.primary_topic) || topicMap.get((p.topics || [])[0]) || topicMap.get("Misc.") || topicNodes[0];
      const angle = (i * 137.508) * Math.PI / 180;
      const radius = 38 + (i % 9) * 9;
      return {
        ...p,
        kind: "paper",
        x: parent.fx + Math.cos(angle) * radius,
        y: parent.fy + Math.sin(angle) * radius
      };
    });
    const paperMap = new Map(paperNodes.map(p => [p.id, p]));
    const nodes = [...topicNodes, ...paperNodes];

    const topicEdges = state.topics.edges.map(e => ({...e, source: e.source, target: e.target, kind: "topic-link"}));
    const paperEdges = [];
    paperNodes.forEach(p => {
      const ts = (p.topics && p.topics.length) ? p.topics : [p.primary_topic || "Misc."];
      ts.forEach((t, idx) => {
        if (topicMap.has(t)) paperEdges.push({source: t, target: p.id, type: idx === 0 ? "primary" : "secondary", kind: "paper-link"});
      });
    });
    const links = [...topicEdges, ...paperEdges];

    const linkLayer = svg.append("g").attr("class", "links");
    const nodeLayer = svg.append("g").attr("class", "nodes");

    const link = linkLayer.selectAll("line")
      .data(links)
      .join("line")
      .attr("class", d => `research-link ${d.kind} ${d.type || ""}`)
      .attr("stroke", d => d.kind === "topic-link" ? "rgba(0,0,0,0.38)" : "rgba(0,0,0,0.13)")
      .attr("stroke-width", d => d.type === "hierarchy" ? 1.8 : d.type === "bridge" ? 1.1 : d.type === "primary" ? 0.8 : 0.45)
      .attr("stroke-dasharray", d => d.type === "bridge" || d.type === "secondary" ? "4 4" : null)
      .attr("marker-end", d => d.kind === "topic-link" ? "url(#arrow)" : null);

    const node = nodeLayer.selectAll("g")
      .data(nodes, d => d.id)
      .join("g")
      .attr("class", d => `research-node ${d.kind}`)
      .on("click", (event, d) => {
        if (d.kind === "paper") showPaper(d);
        else showTopic(d, topicCounts.get(d.id) || 0);
      })
      .call(d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended));

    node.append("circle")
      .attr("r", nodeRadius)
      .attr("fill", d => {
        if (d.kind === "root") return TOPIC_COLORS[d.id] || "#222";
        if (d.kind === "topic") return TOPIC_COLORS[d.id] || "#567";
        return TOPIC_COLORS[d.primary_topic] || "#d58139";
      })
      .attr("stroke", d => d.kind === "paper" ? "rgba(255,255,255,0.95)" : "rgba(0,0,0,0.28)")
      .attr("stroke-width", d => d.kind === "paper" ? 1.4 : 1.1)
      .attr("opacity", d => d.kind === "paper" ? 0.86 : 0.96);

    node.append("title").text(d => d.kind === "paper" ? `${d.title}\n${d.year || ""} · ${(d.topics || []).join(" · ")}` : d.label || d.id);

    node.append("text")
      .attr("dy", d => d.kind === "paper" ? -nodeRadius(d) - 4 : nodeRadius(d) + 15)
      .attr("text-anchor", "middle")
      .attr("font-size", d => d.kind === "root" ? 14 : d.kind === "topic" ? 11.5 : 9.5)
      .attr("font-weight", d => d.kind === "paper" ? 400 : 700)
      .attr("fill", "rgba(0,0,0,0.76)")
      .each(function(d) { wrapSvgText(d3.select(this), d.kind === "paper" ? shortTitle(d.title) : (d.label || d.id), d.kind === "root" ? 145 : d.kind === "topic" ? 130 : 82, d.kind === "paper" ? 2 : 2); });

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.kind === "topic-link" ? 90 : d.type === "primary" ? 52 : 78).strength(d => d.kind === "topic-link" ? 0.12 : d.type === "primary" ? 0.20 : 0.045))
      .force("charge", d3.forceManyBody().strength(d => d.kind === "paper" ? -45 : -260))
      .force("collision", d3.forceCollide().radius(d => nodeRadius(d) + (d.kind === "paper" ? 8 : 20)).iterations(2))
      .force("x", d3.forceX(d => d.kind === "paper" ? ((topicMap.get(d.primary_topic) || topicMap.get("Misc.") || topicNodes[0]).fx) : d.fx).strength(d => d.kind === "paper" ? 0.04 : 0.5))
      .force("y", d3.forceY(d => d.kind === "paper" ? ((topicMap.get(d.primary_topic) || topicMap.get("Misc.") || topicNodes[0]).fy + 70) : d.fy).strength(d => d.kind === "paper" ? 0.04 : 0.5));

    simulation.on("tick", () => {
      nodes.forEach(d => {
        d.x = Math.max(nodeRadius(d) + 4, Math.min(width - nodeRadius(d) - 4, d.x));
        d.y = Math.max(nodeRadius(d) + 4, Math.min(height - nodeRadius(d) - 4, d.y));
      });
      link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.25).restart();
      d.fx = d.x;
      d.fy = d.y;
    }
    function dragged(event, d) {
      d.fx = event.x;
      d.fy = event.y;
    }
    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      if (d.kind === "paper") { d.fx = null; d.fy = null; }
    }
  }

  function shortTitle(title) {
    const s = String(title || "");
    return s.length > 54 ? s.slice(0, 52) + "…" : s;
  }

  function wrapSvgText(textSelection, text, width, maxLines) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    const lineHeight = 1.05;
    textSelection.text(null);
    let line = [];
    let lineNumber = 0;
    const y = textSelection.attr("y") || 0;
    const dy = parseFloat(textSelection.attr("dy")) || 0;
    let tspan = textSelection.append("tspan").attr("x", 0).attr("y", y).attr("dy", dy + "px");
    for (let i = 0; i < words.length; i++) {
      line.push(words[i]);
      tspan.text(line.join(" "));
      if (tspan.node().getComputedTextLength() > width && line.length > 1) {
        line.pop();
        tspan.text(line.join(" "));
        line = [words[i]];
        lineNumber += 1;
        if (lineNumber >= maxLines) {
          tspan.text(tspan.text().replace(/\s*$/, "") + "…");
          break;
        }
        tspan = textSelection.append("tspan").attr("x", 0).attr("y", y).attr("dy", (dy + lineNumber * 12 * lineHeight) + "px").text(words[i]);
      }
    }
  }

  async function init() {
    const svg = byId(SVG_ID);
    if (!svg) return;
    try {
      const [pubResp, topicResp] = await Promise.all([fetch(DATA_URL, {cache: "no-store"}), fetch(TOPIC_URL, {cache: "no-store"})]);
      if (!pubResp.ok || !topicResp.ok) throw new Error("Could not load publication data.");
      const pubData = await pubResp.json();
      const topicData = await topicResp.json();
      state.publications = (pubData.papers || []).filter(p => p && p.title);
      state.generatedAt = pubData.generated_at || "";
      state.topics = topicData;
      populateControls();
      showTopic({id: "Research Map", label: "Research Map", root: "Scholar-synced publication graph"}, state.publications.length);
      render();
      window.addEventListener("resize", () => window.requestAnimationFrame(render));
    } catch (err) {
      const status = byId("research-map-status");
      if (status) status.textContent = "Publication metadata could not be loaded. Check data/publications.json.";
      console.error(err);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();

