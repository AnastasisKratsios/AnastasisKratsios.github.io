(function () {
  const PUBLICATIONS_URL = "data/publications.json";
  const TALKS_URL = "data/upcoming_talks.json";
  const FIELDS_URL = "https://www.fields.utoronto.ca/activities/25-26/mathai";

  function byId(id) { return document.getElementById(id); }

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));
  }

  function normalizeDateLike(value) {
    if (!value) return 0;
    const t = Date.parse(value);
    return Number.isNaN(t) ? 0 : t;
  }

  function arxivMonthScore(id) {
    const match = String(id || "").match(/^(\d{2})(\d{2})\./);
    if (!match) return 0;
    const yy = Number(match[1]);
    const mm = Number(match[2]);
    const year = yy >= 91 ? 1900 + yy : 2000 + yy;
    return Date.UTC(year, Math.max(0, mm - 1), 1);
  }

  function paperScore(p) {
    return normalizeDateLike(p.published || p.updated || p.publication_date || p.date) || arxivMonthScore(p.arxiv_id) || Date.UTC(Number(p.year || 0), 0, 1);
  }

  async function loadJson(url) {
    const resp = await fetch(url, {cache: "no-store"});
    if (!resp.ok) throw new Error(`Could not load ${url}`);
    return resp.json();
  }

  function renderHotPapers(data) {
    const el = byId("hot-off-press-list");
    if (!el) return;
    const papers = (data.papers || [])
      .filter(p => p && p.title)
      .sort((a, b) => paperScore(b) - paperScore(a) || String(a.title).localeCompare(String(b.title)))
      .slice(0, 3);
    if (!papers.length) {
      el.innerHTML = `<p>The latest papers will appear here once <code>data/publications.json</code> is refreshed.</p>`;
      return;
    }
    el.innerHTML = papers.map(p => {
      const title = p.url
        ? `<a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>`
        : escapeHtml(p.title);
      const meta = [p.authors, p.venue, p.year].filter(Boolean).map(escapeHtml).join(" · ");
      const cats = (p.arxiv_categories || []).slice(0, 4).map(c => `<span class="research-subject-badge">${escapeHtml(c)}</span>`).join(" ");
      return `<article class="dynamic-paper-item"><h3>${title}</h3><p>${meta}</p>${cats ? `<p>${cats}</p>` : ""}</article>`;
    }).join("");
  }


  function isJmlrPaper(p) {
    const haystack = String([p.venue, p.journal, p.publisher, p.url, p.source].filter(Boolean).join(" ")).toLowerCase();
    return haystack.includes("journal of machine learning research") ||
      haystack.includes("jmlr") ||
      haystack.includes("jmlr.org/papers");
  }

  function renderSelectedJmlrPapers(data) {
    const el = byId("select-publications-list");
    if (!el) return;
    const papers = (data.papers || [])
      .filter(p => p && p.title && isJmlrPaper(p))
      .sort((a, b) => paperScore(b) - paperScore(a) || String(a.title).localeCompare(String(b.title)))
      .slice(0, 6);
    if (!papers.length) {
      el.innerHTML = `<p>JMLR papers will appear here once the Scholar/arXiv metadata refreshes. <a href="https://scholar.google.ca/citations?hl=en&user=9D-bHFgAAAAJ&view_op=list_works&sortby=pubdate" target="_blank" rel="noopener">Open the Scholar profile</a>.</p>`;
      return;
    }
    el.innerHTML = papers.map(p => {
      const title = p.url
        ? `<a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>`
        : escapeHtml(p.title);
      const meta = [p.authors, p.venue || "Journal of Machine Learning Research", p.year].filter(Boolean).map(escapeHtml).join(" · ");
      return `<article class="dynamic-paper-item select-paper-item"><h3>${title}</h3><p>${meta}</p></article>`;
    }).join("");
  }

  function renderTalks(data) {
    const el = byId("upcoming-talks-list");
    if (!el) return;
    const talks = (data.talks || []).filter(t => t && (t.title || t.speaker || t.date));
    const t = talks[0];
    if (!t) {
      el.innerHTML = `<a class="talk-bubble" href="${FIELDS_URL}" target="_blank" rel="noopener"><span class="talk-bubble-kicker">Upcoming talk</span><strong>Open the Fields seminar page</strong><span>Talk details will appear here once the page refreshes.</span></a>`;
      return;
    }
    const label = [t.date, t.time].filter(Boolean).map(escapeHtml).join(" · ");
    const speaker = t.speaker ? `<span>${escapeHtml(t.speaker)}</span>` : "";
    const title = t.title ? escapeHtml(t.title) : "Upcoming seminar talk";
    const url = t.url || FIELDS_URL;
    el.innerHTML = `<a class="talk-bubble" href="${escapeHtml(url)}" target="_blank" rel="noopener"><span class="talk-bubble-kicker">Upcoming talk</span><strong>${title}</strong>${speaker}${label ? `<span>${label}</span>` : ""}</a>`;
  }

  async function init() {
    loadJson(PUBLICATIONS_URL).then(data => { renderHotPapers(data); renderSelectedJmlrPapers(data); }).catch(() => {
      const el = byId("hot-off-press-list");
      if (el) el.innerHTML = `<p>Latest papers could not be loaded. <a href="https://scholar.google.ca/citations?hl=en&user=9D-bHFgAAAAJ&view_op=list_works&sortby=pubdate" target="_blank" rel="noopener">Open Google Scholar</a>.</p>`;
      const selectEl = byId("select-publications-list");
      if (selectEl) selectEl.innerHTML = `<p>JMLR papers could not be loaded. <a href="https://scholar.google.ca/citations?hl=en&user=9D-bHFgAAAAJ&view_op=list_works&sortby=pubdate" target="_blank" rel="noopener">Open Google Scholar</a>.</p>`;
    });
    loadJson(TALKS_URL).then(renderTalks).catch(() => renderTalks({talks: []}));
  }

  document.addEventListener("DOMContentLoaded", init);
})();
