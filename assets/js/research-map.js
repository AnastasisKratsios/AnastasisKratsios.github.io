(function () {
  const SVG_ID = "research-map-canvas";
  const DATA_URL = "data/publications.json";
  const TOPIC_URL = "data/research_topics.json";

  const TOPIC_COLORS = {
    "AI Theory": "#2f4f9f",
    "Applications": "#91551f",
    "Universal Neural Approximation": "#4768c5",
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

  const AI_TOPICS = [
    "Universal Neural Approximation",
    "Statistical Learning Theory",
    "Reasoning & Computation",
    "Operator Learning",
    "Geometric Deep Learning"
  ];
  const APPLICATION_TOPICS = ["PDEs", "Control & Optimization", "Games & BSDEs", "Finance", "Misc."];
  const TOPIC_ALIASES = {"Approximation Theory": "Universal Neural Approximation", "Learning Theory": "Statistical Learning Theory"};

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

  function canonicalTopic(topic) {
    return TOPIC_ALIASES[topic] || topic;
  }

  function canonicalizePaper(p) {
    const topics = (p.topics || []).map(canonicalTopic);
    const primary = canonicalTopic(p.primary_topic || topics[0] || "Misc.");
    return {...p, topics: Array.from(new Set(topics.length ? topics : [primary])), primary_topic: primary};
  }

  function paperMatches(p) {
    const q = normalize(state.search).trim();
    const text = normalize([
      p.title,
      p.authors,
      p.venue,
      (p.topics || []).join(" "),
      (p.arxiv_categories || []).join(" "),
      p.arxiv_id || ""
    ].join(" "));
    if (q && !text.includes(q)) return false;
    if (state.year !== "all" && String(p.year || "") !== String(state.year)) return false;
    if (state.filter === "all") return true;
    if (state.filter === "AI Theory") return (p.topics || []).some(t => AI_TOPICS.includes(t));
    if (state.filter === "Applications") return (p.topics || []).some(t => APPLICATION_TOPICS.includes(t));
    return (p.topics || []).includes(state.filter) || p.primary_topic === state.filter;
  }

  function setStatus() {
    const el = byId("research-map-status");
    if (!el) return;
    const papers = state.publications.filter(paperMatches);
    const generated = state.generatedAt && state.generatedAt !== "seed" ? ` Last updated: ${state.generatedAt}.` : "";
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

  function topicBadges(topics) {
    return (topics || []).map(t => `<span class="research-topic-badge">${escapeHtml(t)}</span>`).join(" ");
  }

  function subjectBadges(categories) {
    const cats = (categories || []).filter(Boolean);
    if (!cats.length) return "";
    return `<div><strong>Subjects:</strong> ${cats.map(c => `<span class="research-subject-badge">${escapeHtml(c)}</span>`).join(" ")}</div>`;
  }

  function showPaper(p) {
    state.selected = p;
    const panel = byId("research-map-details");
    if (!panel) return;
    const link = p.url ? `<a class="paper-link" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">Open paper/source</a>` : "";
    panel.innerHTML = `
      <h3>${escapeHtml(p.title)}</h3>
      <p class="paper-meta">${escapeHtml(p.authors || "")}${p.authors ? "<br>" : ""}${escapeHtml([p.venue, p.year].filter(Boolean).join(" · "))}${p.citations ? ` · ${escapeHtml(p.citations)} citations` : ""}</p>
      <div>${topicBadges(p.topics)}</div>
      ${subjectBadges(p.arxiv_categories)}
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
        const subjects = (p.arxiv_categories || []).length ? ` · subjects: ${(p.arxiv_categories || []).map(escapeHtml).join(" · ")}` : "";
        html += `<li>${title}. <em>${escapeHtml(p.venue || "")}</em>${p.citations ? ` · ${escapeHtml(p.citations)} citations` : ""}<br><small>${(p.topics || []).map(escapeHtml).join(" · ")}${subjects}</small></li>`;
      });
      html += `</ul></details>`;
    });
    container.innerHTML = html;
  }

  function nodeRadius(d) {
    if (d.kind === "root") return 25;
    if (d.kind === "topic") return 18;
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
    const width = Math.max(760, wrap ? wrap.clientWidth : 1040);
    const height = Math.max(560, svgEl.clientHeight || 672);
    const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();

    const defs = svg.append("defs");
    defs.append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 23)
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
      const radius = 40 + (i % 9) * 10;
      return {
        ...p,
        kind: "paper",
        x: parent.fx + Math.cos(angle) * radius,
        y: parent.fy + Math.sin(angle) * radius
      };
    });
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
      .attr("stroke", d => d.kind === "topic-link" ? "rgba(0,0,0,0.38)" : "rgba(0,0,0,0.12)")
      .attr("stroke-width", d => d.type === "hierarchy" ? 1.8 : d.type === "bridge" ? 1.1 : d.type === "primary" ? 0.75 : 0.4)
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
      .attr("opacity", d => d.kind === "paper" ? 0.88 : 0.96);

    node.append("title").text(d => d.kind === "paper" ? `${d.title}\n${d.year || ""} · ${(d.topics || []).join(" · ")}\n${(d.arxiv_categories || []).join(" · ")}` : d.label || d.id);

    node.filter(d => d.kind !== "paper")
      .append("text")
      .attr("dy", d => nodeRadius(d) + 15)
      .attr("text-anchor", "middle")
      .attr("font-size", d => d.kind === "root" ? 14 : 11.5)
      .attr("font-weight", 700)
      .attr("fill", "rgba(0,0,0,0.76)")
      .each(function(d) { wrapSvgText(d3.select(this), d.label || d.id, d.kind === "root" ? 145 : 150, 2); });

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.kind === "topic-link" ? 96 : d.type === "primary" ? 54 : 80).strength(d => d.kind === "topic-link" ? 0.12 : d.type === "primary" ? 0.22 : 0.045))
      .force("charge", d3.forceManyBody().strength(d => d.kind === "paper" ? -48 : -280))
      .force("collision", d3.forceCollide().radius(d => nodeRadius(d) + (d.kind === "paper" ? 5 : 22)).iterations(2))
      .force("x", d3.forceX(d => d.kind === "paper" ? ((topicMap.get(d.primary_topic) || topicMap.get("Misc.") || topicNodes[0]).fx) : d.fx).strength(d => d.kind === "paper" ? 0.045 : 0.5))
      .force("y", d3.forceY(d => d.kind === "paper" ? ((topicMap.get(d.primary_topic) || topicMap.get("Misc.") || topicNodes[0]).fy + 76) : d.fy).strength(d => d.kind === "paper" ? 0.045 : 0.5));

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
      state.publications = (pubData.papers || []).filter(p => p && p.title).map(canonicalizePaper);
      state.generatedAt = pubData.generated_at || "";
      state.topics = topicData;
      populateControls();
      showTopic({id: "Research Map", label: "Research Map", root: "Scholar/arXiv-synced publication graph"}, state.publications.length);
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
