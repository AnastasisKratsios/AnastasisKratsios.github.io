(function () {
  const DATA_URL = "data/publications.json";
  const TARGET_ID = "hot-press-list";

  function byId(id) { return document.getElementById(id); }
  function escapeHtml(str) {
    return String(str || "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));
  }
  function arxivSortScore(id) {
    const m = String(id || "").match(/^(\d{2})(\d{2})\.(\d+)/);
    if (!m) return 0;
    return Number(`20${m[1]}${m[2]}${m[3].padStart(5, "0")}`);
  }
  function paperSortScore(p) {
    const date = p.published || p.publication_date || p.updated || "";
    const t = Date.parse(date);
    const arxiv = arxivSortScore(p.arxiv_id);
    if (!Number.isNaN(t)) return t + arxiv;
    if (arxiv) return arxiv;
    return Number(p.year || 0) * 100000;
  }
  function render(papers) {
    const el = byId(TARGET_ID);
    if (!el) return;
    const latest = (papers || [])
      .filter(p => p && p.title)
      .sort((a, b) => paperSortScore(b) - paperSortScore(a) || String(a.title).localeCompare(String(b.title)))
      .slice(0, 3);
    if (!latest.length) {
      el.innerHTML = "<p>Latest publication metadata is not available yet.</p>";
      return;
    }
    el.innerHTML = latest.map(p => {
      const title = p.url
        ? `<a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>`
        : escapeHtml(p.title);
      const venueYear = [p.venue, p.year].filter(Boolean).join(" · ");
      const authors = p.authors ? `<p>${escapeHtml(p.authors)}</p>` : "";
      const subjects = (p.arxiv_categories || []).length ? `<p class="hot-press-meta">Subjects: ${(p.arxiv_categories || []).map(escapeHtml).join(" · ")}</p>` : "";
      return `<article><h3>${title}</h3>${authors}<p class="hot-press-meta">${escapeHtml(venueYear)}</p>${subjects}</article>`;
    }).join("");
  }
  async function init() {
    const el = byId(TARGET_ID);
    if (!el) return;
    try {
      const resp = await fetch(DATA_URL, {cache: "no-store"});
      if (!resp.ok) throw new Error("Could not load publications.json");
      const data = await resp.json();
      render(data.papers || []);
    } catch (err) {
      el.innerHTML = "<p>Latest papers could not be loaded. Please use the Google Scholar link below.</p>";
      console.error(err);
    }
  }
  document.addEventListener("DOMContentLoaded", init);
})();
