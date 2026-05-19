#!/usr/bin/env python3
"""Refresh data/publications.json from Google Scholar.

Primary source: the Google Scholar profile identified by SCHOLAR_USER_ID.
Optional enrichment: Semantic Scholar and OpenAlex title search can add abstracts,
DOIs, venues, and stable URLs when available.

The script is intentionally fail-safe for GitHub Pages: if Scholar or an
external service blocks a run, it preserves the existing publications.json and
exits successfully unless REQUIRE_SUCCESS=1 is set. This keeps the website from
breaking while still making the update path fully automated.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import requests
except Exception as exc:  # pragma: no cover
    print(f"requests is required: {exc}", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "publications.json"
OVERRIDES_PATH = ROOT / "data" / "publication_overrides.json"
SCHOLAR_USER_ID = os.environ.get("SCHOLAR_USER_ID", "9D-bHFgAAAAJ")
SCHOLAR_PROFILE = f"https://scholar.google.ca/citations?user={SCHOLAR_USER_ID}&hl=en"
MAX_PUBLICATIONS = int(os.environ.get("MAX_PUBLICATIONS", "250"))
ENRICH_LIMIT = int(os.environ.get("ENRICH_LIMIT", "120"))
REQUIRE_SUCCESS = os.environ.get("REQUIRE_SUCCESS", "0") == "1"
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
USER_AGENT = os.environ.get("PUBLICATION_UPDATER_USER_AGENT", "AnastasisKratsios.github.io publication updater (mailto:kratsiosanastasis@gmail.com)")

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "Approximation Theory": ["approximation", "universal", "relu", "mlp", "transformer", "constraints", "representation", "regular conditional", "density", "curse of dimensionality", "mixture of experts", "sub-patterns"],
    "Statistical Learning Theory": ["generalization", "learning curve", "kernel ridge", "ridgeless", "vc", "pac", "risk bound", "risk bounds", "sample complexity", "overfitting", "statistical", "optimal transport", "finite-rank", "test error"],
    "Reasoning & Computation": ["reasoning", "compute", "computation", "in-context", "algorithm", "algorithms", "digital computers", "universal metric embeddings", "transformers compute"],
    "Operator Learning": ["operator", "operators", "neural operator", "deeponet", "fno", "helmholtz", "solution operator", "rank", "logarithmic depth"],
    "Geometric Deep Learning": ["geometric", "graph", "graphs", "hyperbolic", "manifold", "metric space", "metric space-valued", "dag", "message passing", "latent graph", "spacetime", "spacetimes", "snowflake"],
    "PDEs": ["pde", "pdes", "helmholtz", "volterra", "stochastic analysis", "filter", "filtering", "kalman", "dynamical systems", "processes"],
    "Control & Optimization": ["control", "optimization", "optimizers", "regret", "gradient descent", "federated", "transfer learning", "barycenter", "optimal", "online gating"],
    "Games & BSDEs": ["game", "games", "stackelberg", "nash", "bsde", "bsdes", "fbsde"],
    "Finance": ["finance", "financial", "option", "options", "pricing", "american option", "arbitrage", "hjm", "risk", "market", "causal", "adapted", "stochastic finance"],
}
ROOT_TOPICS = {
    "AI Theory": {"Approximation Theory", "Statistical Learning Theory", "Reasoning & Computation", "Operator Learning", "Geometric Deep Learning"},
    "Applications": {"PDEs", "Control & Optimization", "Games & BSDEs", "Finance", "Misc."},
}


def normalize(text: Any) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-")[:72]
    return base or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def infer_topics(title: str, abstract: str = "", venue: str = "") -> Tuple[List[str], str, str]:
    text = f" {normalize(title)} {normalize(abstract)} {normalize(venue)} "
    scores: Dict[str, int] = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            key = normalize(keyword)
            if not key:
                continue
            if " " in key:
                score += 3 * text.count(key)
            else:
                score += text.count(f" {key} ")
        if score > 0:
            scores[topic] = score

    if "transformer" in text and "Reasoning & Computation" not in scores:
        scores["Reasoning & Computation"] = 1
    if not scores:
        scores["Misc."] = 1

    topics = sorted(scores, key=lambda k: (-scores[k], k))[:4]
    if ("Operator Learning" in topics or "Geometric Deep Learning" in topics) and "Approximation Theory" not in topics:
        topics.append("Approximation Theory")
    if any(marker in text for marker in [" option ", "arbitrage", "hjm", "finance", "market"] ) and "Finance" not in topics:
        topics.append("Finance")

    primary = topics[0]
    root = "Applications" if primary in ROOT_TOPICS["Applications"] else "AI Theory"
    return topics[:5], primary, root


def scholar_publications() -> List[Dict[str, Any]]:
    from scholarly import scholarly  # imported lazily because it is the least stable dependency

    print(f"Fetching Scholar profile {SCHOLAR_USER_ID} ...")
    author = scholarly.search_author_id(SCHOLAR_USER_ID)
    author = scholarly.fill(author, sections=["publications"])
    publications: List[Dict[str, Any]] = []
    for pub in author.get("publications", [])[:MAX_PUBLICATIONS]:
        bib = pub.get("bib", {}) or {}
        title = bib.get("title") or pub.get("title") or ""
        if not title:
            continue
        publications.append({
            "id": slugify(title),
            "title": title,
            "authors": bib.get("author", ""),
            "year": _safe_int(bib.get("pub_year") or bib.get("year")),
            "venue": bib.get("venue", ""),
            "url": pub.get("pub_url", "") or pub.get("eprint_url", ""),
            "citations": _safe_int(pub.get("num_citations"), default=0),
            "abstract": bib.get("abstract", ""),
            "scholar_citation_id": pub.get("author_pub_id", ""),
            "source": "Google Scholar profile",
        })
    return dedupe_by_title(publications)


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def dedupe_by_title(papers: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for paper in papers:
        key = normalize(paper.get("title", ""))
        if not key:
            continue
        old = seen.get(key)
        if old is None or (paper.get("citations") or 0) > (old.get("citations") or 0):
            seen[key] = paper
    return list(seen.values())


def request_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Optional[Dict[str, Any]]:
    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)
    try:
        resp = requests.get(url, headers=merged_headers, timeout=timeout)
        if resp.status_code == 429:
            time.sleep(2.0)
            return None
        if not resp.ok:
            return None
        return resp.json()
    except Exception:
        return None


def enrich_with_semantic_scholar(title: str) -> Dict[str, Any]:
    fields = "title,abstract,year,venue,url,citationCount,authors,externalIds"
    q = urllib.parse.urlencode({"query": title, "limit": 3, "fields": fields})
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    data = request_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{q}", headers=headers)
    if not data:
        return {}
    target = normalize(title)
    best = None
    best_score = 0
    for item in data.get("data", []) or []:
        item_title = normalize(item.get("title", ""))
        if not item_title:
            continue
        overlap = len(set(target.split()) & set(item_title.split()))
        score = overlap / max(1, len(set(target.split()) | set(item_title.split())))
        if score > best_score:
            best, best_score = item, score
    if not best or best_score < 0.58:
        return {}
    authors = best.get("authors") or []
    return {
        "abstract": best.get("abstract") or "",
        "year": _safe_int(best.get("year")),
        "venue": best.get("venue") or "",
        "url": best.get("url") or "",
        "citations": _safe_int(best.get("citationCount"), default=0),
        "authors": ", ".join(a.get("name", "") for a in authors if a.get("name")),
        "doi": (best.get("externalIds") or {}).get("DOI", ""),
        "semantic_scholar_id": best.get("paperId", ""),
    }


def enrich_with_openalex(title: str) -> Dict[str, Any]:
    q = urllib.parse.urlencode({"search": title, "per-page": 3, "mailto": "kratsiosanastasis@gmail.com"})
    data = request_json(f"https://api.openalex.org/works?{q}")
    if not data:
        return {}
    target = normalize(title)
    best = None
    best_score = 0
    for item in data.get("results", []) or []:
        item_title = normalize(item.get("display_name", ""))
        if not item_title:
            continue
        score = len(set(target.split()) & set(item_title.split())) / max(1, len(set(target.split()) | set(item_title.split())))
        if score > best_score:
            best, best_score = item, score
    if not best or best_score < 0.58:
        return {}
    abstract = inverted_index_to_text(best.get("abstract_inverted_index") or {})
    authorships = best.get("authorships") or []
    authors = ", ".join((a.get("author") or {}).get("display_name", "") for a in authorships if (a.get("author") or {}).get("display_name"))
    primary_location = best.get("primary_location") or {}
    source = primary_location.get("source") or {}
    return {
        "abstract": abstract,
        "year": _safe_int(best.get("publication_year")),
        "venue": source.get("display_name", ""),
        "url": best.get("doi") or best.get("id") or "",
        "citations": _safe_int(best.get("cited_by_count"), default=0),
        "authors": authors,
        "doi": str(best.get("doi") or "").replace("https://doi.org/", ""),
        "openalex_id": best.get("id", ""),
    }


def inverted_index_to_text(index: Dict[str, List[int]]) -> str:
    if not index:
        return ""
    pairs = []
    for word, positions in index.items():
        for pos in positions:
            pairs.append((pos, word))
    return " ".join(word for _, word in sorted(pairs))


def enrich(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []
    for i, paper in enumerate(papers):
        p = dict(paper)
        if i < ENRICH_LIMIT:
            extra = enrich_with_semantic_scholar(p["title"])
            time.sleep(0.25)
            if not extra:
                extra = enrich_with_openalex(p["title"])
                time.sleep(0.1)
            for key, value in extra.items():
                if value not in (None, "", 0):
                    if key == "citations":
                        p[key] = max(_safe_int(p.get(key), 0) or 0, _safe_int(value, 0) or 0)
                    elif not p.get(key):
                        p[key] = value
        enriched.append(p)
    return enriched


def apply_overrides(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    overrides = load_json(OVERRIDES_PATH, {})
    topic_overrides = overrides.get("topic_overrides", {}) or {}
    url_overrides = overrides.get("url_overrides", {}) or {}
    venue_overrides = overrides.get("venue_overrides", {}) or {}
    for p in papers:
        key = normalize(p.get("title", ""))
        if key in url_overrides:
            p["url"] = url_overrides[key]
        if key in venue_overrides:
            p["venue"] = venue_overrides[key]
        if key in topic_overrides:
            p["topics"] = topic_overrides[key]
            p["primary_topic"] = p["topics"][0] if p["topics"] else "Misc."
            p["root"] = "Applications" if p["primary_topic"] in ROOT_TOPICS["Applications"] else "AI Theory"
    return papers


def finalize(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for paper in dedupe_by_title(papers):
        p = dict(paper)
        p["id"] = p.get("id") or slugify(p.get("title", ""))
        p["year"] = _safe_int(p.get("year"))
        p["citations"] = _safe_int(p.get("citations"), default=0) or 0
        p["authors"] = p.get("authors") or ""
        p["venue"] = p.get("venue") or ""
        p["url"] = p.get("url") or ""
        p["abstract"] = p.get("abstract") or ""
        topics, primary, root = infer_topics(p["title"], p.get("abstract", ""), p.get("venue", ""))
        p.setdefault("topics", topics)
        if not p.get("topics"):
            p["topics"] = topics
        p["primary_topic"] = p.get("primary_topic") or primary
        p["root"] = p.get("root") or root
        out.append(p)
    out = apply_overrides(out)
    return sorted(out, key=lambda p: (-(p.get("year") or 0), -int(p.get("citations") or 0), p.get("title", "")))


def write_data(papers: List[Dict[str, Any]], source_note: str) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": now_iso(),
        "source": source_note,
        "scholar_user_id": SCHOLAR_USER_ID,
        "scholar_profile": SCHOLAR_PROFILE,
        "papers": papers,
    }
    DATA_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(papers)} publications to {DATA_PATH}")


def preserve_existing(reason: str) -> int:
    print(f"Publication refresh failed: {reason}", file=sys.stderr)
    if REQUIRE_SUCCESS:
        return 1
    if DATA_PATH.exists():
        print("Preserving existing data/publications.json.")
        return 0
    fallback = []
    write_data(fallback, f"Empty fallback after failed update: {reason}")
    return 0


def main() -> int:
    try:
        papers = scholar_publications()
        if not papers:
            return preserve_existing("Scholar returned no publications")
        papers = enrich(papers)
        papers = finalize(papers)
        write_data(papers, "Google Scholar profile, enriched by Semantic Scholar/OpenAlex when available")
        return 0
    except Exception as exc:
        return preserve_existing(repr(exc))


if __name__ == "__main__":
    raise SystemExit(main())

