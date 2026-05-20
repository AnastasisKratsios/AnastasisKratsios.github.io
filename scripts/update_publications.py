#!/usr/bin/env python3
"""Refresh data/publications.json from Google Scholar and arXiv.

Primary intent: keep the website fully automated.  Google Scholar remains the
canonical profile requested by the site owner, while arXiv is used as the most
reliable structured source for preprints, arXiv identifiers, and arXiv subject
classes.  The arXiv subject classes are then mapped into the high-level research
DAG used by the website.

The script is fail-safe for GitHub Pages: if a source blocks a run, the existing
publications.json is preserved unless REQUIRE_SUCCESS=1 is set.
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
import xml.etree.ElementTree as ET
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
ARXIV_AUTHOR_QUERY = os.environ.get("ARXIV_AUTHOR_QUERY", "au:Kratsios_A")
MAX_PUBLICATIONS = int(os.environ.get("MAX_PUBLICATIONS", "300"))
ARXIV_MAX_RESULTS = int(os.environ.get("ARXIV_MAX_RESULTS", "200"))
ENRICH_LIMIT = int(os.environ.get("ENRICH_LIMIT", "120"))
REQUIRE_SUCCESS = os.environ.get("REQUIRE_SUCCESS", "0") == "1"
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
USER_AGENT = os.environ.get(
    "PUBLICATION_UPDATER_USER_AGENT",
    "AnastasisKratsios.github.io publication updater (mailto:kratsiosanastasis@gmail.com)",
)

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "Universal Neural Approximation": [
        "approximation", "universal", "universality", "relu", "mlp", "kan", "kolmogorov",
        "transformer", "constraints", "representation", "regular conditional", "density",
        "curse of dimensionality", "mixture of experts", "sub-pattern", "sub patterns",
        "besov", "holder", "neural network", "flow-based", "generative", "optimal approximation",
    ],
    "Statistical Learning Theory": [
        "generalization", "learning curve", "kernel ridge", "ridgeless", "vc", "pac",
        "risk bound", "risk bounds", "sample complexity", "overfitting", "statistical",
        "optimal transport", "finite-rank", "test error", "concentration", "lora", "low-rank",
        "foundation model", "classification", "clustering", "probe",
    ],
    "Reasoning & Computation": [
        "reasoning", "compute", "computation", "in-context", "algorithm", "algorithms",
        "digital computers", "boolean", "circuit", "circuits", "turing", "recursive",
        "metric embeddings", "transformers compute", "agentic", "realizability", "lora",
    ],
    "Operator Learning": [
        "operator", "operators", "neural operator", "deeponet", "fno", "helmholtz",
        "solution operator", "rank", "log-complexity", "logarithmic", "causal neural operator",
        "2bsde", "bsde families", "functional clusters",
    ],
    "Geometric Deep Learning": [
        "geometric", "graph", "graphs", "gnn", "hyperbolic", "manifold", "metric space",
        "metric space-valued", "dag", "message passing", "latent graph", "spacetime", "spacetimes",
        "snowflake", "tree", "non-positive curvature", "volterra", "wasserstein", "barycenter",
    ],
    "PDEs": [
        "pde", "pdes", "helmholtz", "elliptic", "green", "volterra", "stochastic analysis",
        "filter", "filtering", "kalman", "dynamical systems", "processes", "rough differential",
    ],
    "Control & Optimization": [
        "control", "optimization", "optimizers", "regret", "gradient descent", "federated",
        "transfer learning", "barycenter", "optimal", "online gating", "convex", "lipschitz",
        "reconstruction", "mean-field", "mean field", "reinforcement", "equilibrium",
    ],
    "Games & BSDEs": [
        "game", "games", "stackelberg", "nash", "mean field game", "mfg", "bsde", "bsdes",
        "fbsde", "2bsde", "equilibrium", "agents", "agentic", "federated",
    ],
    "Finance": [
        "finance", "financial", "option", "options", "pricing", "american option", "arbitrage",
        "hjm", "risk", "market", "markets", "causal", "adapted", "stochastic finance",
        "volatility", "hedging", "liquidity", "contingent claims", "q-fin", "market movement",
    ],
}
ROOT_TOPICS = {
    "AI Theory": {"Universal Neural Approximation", "Statistical Learning Theory", "Reasoning & Computation", "Operator Learning", "Geometric Deep Learning"},
    "Applications": {"PDEs", "Control & Optimization", "Games & BSDEs", "Finance", "Misc."},
}
TOPIC_ALIASES = {"Approximation Theory": "Universal Neural Approximation", "Learning Theory": "Statistical Learning Theory"}

ARXIV_CATEGORY_TOPIC_HINTS: Dict[str, List[str]] = {
    "q-fin": ["Finance"],
    "q-fin.CP": ["Finance"],
    "q-fin.MF": ["Finance"],
    "q-fin.PR": ["Finance"],
    "math.OC": ["Control & Optimization"],
    "math.AP": ["PDEs"],
    "math.PR": ["PDEs", "Games & BSDEs"],
    "math.NA": ["Universal Neural Approximation"],
    "math.FA": ["Universal Neural Approximation"],
    "math.MG": ["Geometric Deep Learning"],
    "math.DG": ["Geometric Deep Learning"],
    "math.CO": ["Geometric Deep Learning"],
    "math.DS": ["PDEs", "Control & Optimization"],
    "math.LO": ["Reasoning & Computation"],
    "cs.CC": ["Reasoning & Computation"],
    "cs.LO": ["Reasoning & Computation"],
    "cs.DM": ["Geometric Deep Learning"],
    "cs.GT": ["Games & BSDEs", "Control & Optimization"],
    "cs.CV": ["Statistical Learning Theory"],
    "cs.CL": ["Reasoning & Computation"],
    "cs.AI": ["Reasoning & Computation", "Statistical Learning Theory"],
    "cs.NE": ["Universal Neural Approximation", "Geometric Deep Learning"],
    "cs.LG": ["Statistical Learning Theory", "Universal Neural Approximation"],
    "stat.ML": ["Statistical Learning Theory"],
    "stat.CO": ["Statistical Learning Theory"],
    "math.ST": ["Statistical Learning Theory"],
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


def canonical_topic(topic: str) -> str:
    return TOPIC_ALIASES.get(topic, topic)


def add_score(scores: Dict[str, int], topic: str, score: int) -> None:
    topic = canonical_topic(topic)
    scores[topic] = scores.get(topic, 0) + score


def infer_topics(title: str, abstract: str = "", venue: str = "", arxiv_categories: Optional[List[str]] = None) -> Tuple[List[str], str, str]:
    categories = [str(c) for c in (arxiv_categories or []) if c]
    text = f" {normalize(title)} {normalize(abstract)} {normalize(venue)} {' '.join(normalize(c) for c in categories)} "
    scores: Dict[str, int] = {}

    # arXiv subjects are treated as the first, structured signal.
    for cat in categories:
        for key, topics in ARXIV_CATEGORY_TOPIC_HINTS.items():
            if cat == key or cat.startswith(key + ".") or (key == "q-fin" and cat.startswith("q-fin")):
                for topic in topics:
                    add_score(scores, topic, 2)

    # Titles/abstracts refine the high-level bucket.
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
            add_score(scores, topic, score)

    # Strong semantic overrides from title phrases.
    if any(x in text for x in [" neural operator ", " neural operators ", " operator learning ", " solution operator "]):
        add_score(scores, "Operator Learning", 8)
    if any(x in text for x in [" graph ", " graphs ", " gnn ", " hyperbolic ", " snowflake ", " spacetime ", " metric space ", " dag ", " message passing "]):
        add_score(scores, "Geometric Deep Learning", 8)
    if any(x in text for x in [" bsde ", " bsdes ", " 2bsde ", " stackelberg ", " nash ", " mean field game "]):
        add_score(scores, "Games & BSDEs", 8)
    if any(x in text for x in [" q fin ", " option ", " options ", " arbitrage ", " market ", " markets ", " finance ", " financial ", " hedging "]):
        add_score(scores, "Finance", 10)
    if any(x in text for x in [" reasoning ", " boolean ", " circuit ", " circuits ", " in context ", " digital computer ", " algorithms "]):
        add_score(scores, "Reasoning & Computation", 8)
    if any(x in text for x in [" generalization ", " sample complexity ", " vc ", " pac ", " learning curve ", " kernel ridge ", " overfitting ", " test error "]):
        add_score(scores, "Statistical Learning Theory", 8)
    if any(x in text for x in [" approximation ", " universal ", " universality ", " relu ", " mlp ", " kan ", " transformer "]):
        add_score(scores, "Universal Neural Approximation", 6)

    if not scores:
        add_score(scores, "Misc.", 1)

    topics = sorted(scores, key=lambda k: (-scores[k], k))[:5]
    if "Operator Learning" in topics and "Universal Neural Approximation" not in topics:
        topics.append("Universal Neural Approximation")
    if "Geometric Deep Learning" in topics and "Universal Neural Approximation" not in topics:
        topics.append("Universal Neural Approximation")
    topics = list(dict.fromkeys(topics))[:5]

    primary = topics[0] if topics else "Misc."
    root = "Applications" if primary in ROOT_TOPICS["Applications"] else "AI Theory"
    return topics, primary, root


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


def arxiv_publications() -> List[Dict[str, Any]]:
    print(f"Fetching arXiv search {ARXIV_AUTHOR_QUERY} ...")
    query = urllib.parse.urlencode({
        "search_query": ARXIV_AUTHOR_QUERY,
        "start": 0,
        "max_results": ARXIV_MAX_RESULTS,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"https://export.arxiv.org/api/query?{query}"
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=45)
    if not resp.ok:
        raise RuntimeError(f"arXiv returned HTTP {resp.status_code}")

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(resp.content)
    papers: List[Dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        title = clean_arxiv_text(entry.findtext("atom:title", default="", namespaces=ns))
        if not title:
            continue
        authors = ", ".join(clean_arxiv_text(a.findtext("atom:name", default="", namespaces=ns)) for a in entry.findall("atom:author", ns))
        authors = ", ".join(a for a in authors.split(", ") if a)
        summary = clean_arxiv_text(entry.findtext("atom:summary", default="", namespaces=ns))
        published = entry.findtext("atom:published", default="", namespaces=ns)
        year = _safe_int(published[:4])
        entry_id = entry.findtext("atom:id", default="", namespaces=ns)
        arxiv_id = entry_id.rstrip("/").split("/")[-1] if entry_id else ""
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        categories = [cat.attrib.get("term", "") for cat in entry.findall("atom:category", ns) if cat.attrib.get("term")]
        primary = entry.find("arxiv:primary_category", ns)
        primary_category = primary.attrib.get("term", "") if primary is not None else (categories[0] if categories else "")
        pdf_url = ""
        html_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else entry_id
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
        papers.append({
            "id": slugify(title),
            "title": title,
            "authors": authors,
            "year": year,
            "venue": "arXiv",
            "url": html_url or pdf_url,
            "citations": 0,
            "abstract": summary,
            "arxiv_id": arxiv_id,
            "arxiv_categories": categories,
            "arxiv_primary_category": primary_category,
            "source": "arXiv author search",
        })
    return dedupe_by_title(papers)


def clean_arxiv_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


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
        else:
            seen[key] = merge_papers(old, paper)
    return list(seen.values())


def merge_papers(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(primary)
    for key, value in secondary.items():
        if value in (None, "", [], 0):
            continue
        if key == "citations":
            merged[key] = max(_safe_int(merged.get(key), 0) or 0, _safe_int(value, 0) or 0)
        elif key == "arxiv_categories":
            merged[key] = list(dict.fromkeys((merged.get(key) or []) + (value or [])))
        elif not merged.get(key):
            merged[key] = value
    return merged


def merge_sources(*paper_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for papers in paper_lists:
        for paper in papers:
            key = normalize(paper.get("title", ""))
            if not key:
                continue
            seen[key] = merge_papers(seen[key], paper) if key in seen else dict(paper)
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
    best_score = 0.0
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
    best_score = 0.0
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
    category_overrides = overrides.get("arxiv_category_overrides", {}) or {}
    year_overrides = overrides.get("year_overrides", {}) or {}
    for p in papers:
        key = normalize(p.get("title", ""))
        if key in url_overrides:
            p["url"] = url_overrides[key]
        if key in venue_overrides:
            p["venue"] = venue_overrides[key]
        if key in year_overrides:
            p["year"] = _safe_int(year_overrides[key], p.get("year"))
        if key in category_overrides:
            p["arxiv_categories"] = category_overrides[key]
        if key in topic_overrides:
            p["topics"] = [canonical_topic(t) for t in topic_overrides[key]]
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
        p["arxiv_categories"] = [str(c) for c in (p.get("arxiv_categories") or []) if c]
        topics, primary, root = infer_topics(p["title"], p.get("abstract", ""), p.get("venue", ""), p.get("arxiv_categories", []))
        p["topics"] = [canonical_topic(t) for t in (p.get("topics") or topics)]
        if not p.get("topics"):
            p["topics"] = topics
        p["primary_topic"] = canonical_topic(p.get("primary_topic") or primary)
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
        "arxiv_author_query": ARXIV_AUTHOR_QUERY,
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
    fallback: List[Dict[str, Any]] = []
    write_data(fallback, f"Empty fallback after failed update: {reason}")
    return 0


def main() -> int:
    scholar_papers: List[Dict[str, Any]] = []
    arxiv_papers: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        scholar_papers = scholar_publications()
    except Exception as exc:
        errors.append(f"Scholar: {exc!r}")

    try:
        arxiv_papers = arxiv_publications()
    except Exception as exc:
        errors.append(f"arXiv: {exc!r}")

    papers = merge_sources(arxiv_papers, scholar_papers)
    if not papers:
        return preserve_existing("; ".join(errors) or "no publications returned")

    try:
        papers = enrich(papers)
    except Exception as exc:
        errors.append(f"Enrichment: {exc!r}")

    papers = finalize(papers)
    note = "Google Scholar profile plus arXiv author search; Semantic Scholar/OpenAlex enrichment when available"
    if errors:
        note += "; warnings: " + "; ".join(errors)
    write_data(papers, note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
