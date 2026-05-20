(function () {
  const DATA_URL = "data/talks.json";
  const TARGET_ID = "fields-talks-list";

  function byId(id) { return document.getElementById(id); }
  function escapeHtml(str) {
    return String(str || "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));
  }
  function dateScore(talk) {
    const raw = talk.date_iso || talk.date || "";
    const parsed = Date.parse(raw);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  function render(talks, sourceUrl) {
    const el = byId(TARGET_ID);
    if (!el) return;
    const items = (talks || [])
      .filter(t => t && t.title)
      .sort((a, b) => dateScore(b) - dateScore(a))
      .slice(0, 6);
    if (!items.length) {
      el.innerHTML = `<p>Talk metadata is not available yet. <a href="${escapeHtml(sourceUrl || 'http://www.fields.utoronto.ca/activities/25-26/mathai')}" target="_blank" rel="noopener">View the Fields page.</a></p>`;
      return;
    }
    el.innerHTML = items.map(t => {
      const title = t.url ? `<a href="${escapeHtml(t.url)}" target="_blank" rel="noopener">${escapeHtml(t.title)}</a>` : escapeHtml(t.title);
      const speaker = t.speaker ? `<p>${escapeHtml(t.speaker)}</p>` : "";
      const meta = [t.date, t.location].filter(Boolean).join(" · ");
      return `<article><h3>${title}</h3>${speaker}<p class="fields-talk-meta">${escapeHtml(meta)}</p></article>`;
    }).join("");
  }
  async function init() {
    const el = byId(TARGET_ID);
    if (!el) return;
    try {
      const resp = await fetch(DATA_URL, {cache: "no-store"});
      if (!resp.ok) throw new Error("Could not load talks.json");
      const data = await resp.json();
      render(data.talks || [], data.source_url);
    } catch (err) {
      el.innerHTML = '<p>Talks could not be loaded. Please use the Fields seminar link below.</p>';
      console.error(err);
    }
  }
  document.addEventListener("DOMContentLoaded", init);
})();
