#!/usr/bin/env python3
"""Build data/collaborations.json for the collaboration world map.

Priority order:
  1. OpenAlex structured institution(s) attached to each authorship/work.
  2. OpenAlex raw affiliation text from that exact work, resolved to institutions.
  3. data/collaboration_fallback.json paper/version-specific arXiv audit.
  4. Current LinkedIn/official affiliations from the fallback file, displayed
     SEPARATELY and never substituted for historical paper-time affiliations.

The fallback is deliberately additive and fail-safe: if OpenAlex is unavailable,
the curated arXiv audit can still populate the historical map.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import os
import re
import time
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS_PATH = ROOT / "data" / "publications.json"
OUTPUT_PATH = ROOT / "data" / "collaborations.json"
OVERRIDES_PATH = ROOT / "data" / "collaboration_overrides.json"
FALLBACK_PATH = ROOT / "data" / "collaboration_fallback.json"

AUTHOR_NAME = os.environ.get("COLLABORATION_AUTHOR_NAME", "Anastasis Kratsios")
OPENALEX_AUTHOR_ID = os.environ.get("OPENALEX_AUTHOR_ID", "").strip()
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
OPENALEX_MAILTO = os.environ.get(
    "OPENALEX_MAILTO", "kratsiosanastasis@gmail.com"
).strip()
USER_AGENT = os.environ.get(
    "COLLABORATION_MAP_USER_AGENT",
    "AnastasisKratsios.github.io collaboration map updater",
)

TITLE_MATCH_THRESHOLD = float(
    os.environ.get("COLLABORATION_TITLE_MATCH_THRESHOLD", "0.72")
)
RAW_AFFILIATION_MATCH_THRESHOLD = float(
    os.environ.get("RAW_AFFILIATION_MATCH_THRESHOLD", "0.58")
)
MAX_OPENALEX_WORKS = int(os.environ.get("MAX_OPENALEX_WORKS", "500"))


def normalize(text: Any) -> str:
    text = (
        unicodedata.normalize("NFKD", str(text or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def slug(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-")


def now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def openalex_url(path: str, params: Optional[Dict[str, Any]] = None) -> str:
    query = dict(params or {})
    if OPENALEX_MAILTO:
        query["mailto"] = OPENALEX_MAILTO
    if OPENALEX_API_KEY:
        query["api_key"] = OPENALEX_API_KEY
    encoded = urllib.parse.urlencode(query, doseq=True)
    return f"https://api.openalex.org/{path}" + (f"?{encoded}" if encoded else "")


def request_json(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(4):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if not response.ok:
                return None
            return response.json()
        except requests.RequestException:
            if attempt == 3:
                return None
            time.sleep(0.5 * (2 ** attempt))
    return None


def strip_openalex_id(value: Any) -> str:
    value = str(value or "").strip()
    return value.rstrip("/").split("/")[-1] if value else ""


def resolve_author_id() -> Optional[str]:
    if OPENALEX_AUTHOR_ID:
        return strip_openalex_id(OPENALEX_AUTHOR_ID)

    data = request_json(
        openalex_url(
            "authors",
            {
                "search": AUTHOR_NAME,
                "per-page": 10,
                "select": "id,display_name,orcid,works_count",
            },
        )
    )
    if not data:
        return None

    target = normalize(AUTHOR_NAME)
    results = data.get("results") or []
    exact = [x for x in results if normalize(x.get("display_name")) == target]
    candidate = exact[0] if exact else (results[0] if results else None)
    return strip_openalex_id((candidate or {}).get("id")) or None


def fetch_author_works(author_id: str) -> List[Dict[str, Any]]:
    works: List[Dict[str, Any]] = []
    page = 1
    per_page = 100

    while len(works) < MAX_OPENALEX_WORKS:
        data = request_json(
            openalex_url(
                "works",
                {
                    "filter": f"authorships.author.id:{author_id}",
                    "per-page": per_page,
                    "page": page,
                    "select": "id,display_name,publication_year,doi,authorships",
                },
            )
        )
        if not data:
            break

        batch = data.get("results") or []
        if not batch:
            break

        works.extend(batch)
        if len(batch) < per_page:
            break
        page += 1

    return works[:MAX_OPENALEX_WORKS]


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    sequence = difflib.SequenceMatcher(None, na, nb).ratio()
    return 0.55 * sequence + 0.45 * jaccard


def score_work_match(paper: Dict[str, Any], work: Dict[str, Any]) -> float:
    score = title_similarity(
        paper.get("title") or "", work.get("display_name") or ""
    )
    if paper.get("year") and work.get("publication_year"):
        try:
            delta = abs(int(paper["year"]) - int(work["publication_year"]))
            if delta == 0:
                score += 0.03
            elif delta > 2:
                score -= 0.08
        except Exception:
            pass
    return min(score, 1.0)


def work_has_self(work: Dict[str, Any], author_id: str) -> bool:
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        if strip_openalex_id(author.get("id")) == author_id:
            return True
        if normalize(author.get("display_name")) == normalize(AUTHOR_NAME):
            return True
    return False


def match_work_from_pool(
    paper: Dict[str, Any], works: Iterable[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], float]:
    doi = normalize(str(paper.get("doi") or "").replace("https://doi.org/", ""))
    best = None
    best_score = 0.0

    for work in works:
        if doi:
            work_doi = normalize(
                str(work.get("doi") or "").replace("https://doi.org/", "")
            )
            if work_doi and work_doi == doi:
                return work, 1.0

        score = score_work_match(paper, work)
        if score > best_score:
            best, best_score = work, score

    if best is not None and best_score >= TITLE_MATCH_THRESHOLD:
        return best, best_score
    return None, best_score


def search_work_by_title(
    paper: Dict[str, Any], author_id: str
) -> Tuple[Optional[Dict[str, Any]], float]:
    title = str(paper.get("title") or "").strip()
    if not title:
        return None, 0.0

    data = request_json(
        openalex_url(
            "works",
            {
                "search": title,
                "per-page": 10,
                "select": "id,display_name,publication_year,doi,authorships",
            },
        )
    )
    if not data:
        return None, 0.0

    candidates = [
        w for w in (data.get("results") or [])
        if work_has_self(w, author_id)
    ]
    return match_work_from_pool(paper, candidates)


def match_work(
    paper: Dict[str, Any],
    author_works: Iterable[Dict[str, Any]],
    author_id: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], float, str]:
    if not author_id:
        return None, 0.0, "openalex-unavailable"

    work, score = match_work_from_pool(paper, author_works)
    if work:
        return work, score, "author-profile"

    work, search_score = search_work_by_title(paper, author_id)
    if work:
        return work, search_score, "title-search"

    return None, max(score, search_score), "unmatched"


def is_self_authorship(authorship: Dict[str, Any], author_id: Optional[str]) -> bool:
    author = authorship.get("author") or {}
    if author_id and strip_openalex_id(author.get("id")) == author_id:
        return True
    return normalize(author.get("display_name")) == normalize(AUTHOR_NAME)


def fetch_institution(institution_id: str) -> Optional[Dict[str, Any]]:
    inst_id = strip_openalex_id(institution_id)
    if not inst_id:
        return None
    return request_json(openalex_url(f"institutions/{inst_id}"))


def raw_affiliation_strings(authorship: Dict[str, Any]) -> List[str]:
    result: List[str] = []
    many = authorship.get("raw_affiliation_strings")
    if isinstance(many, list):
        result.extend(str(x).strip() for x in many if str(x).strip())
    single = authorship.get("raw_affiliation_string")
    if single:
        result.append(str(single).strip())
    return list(dict.fromkeys(result))


def affiliation_match_score(raw: str, institution_name: str) -> float:
    raw_n = normalize(raw)
    name_n = normalize(institution_name)
    if not raw_n or not name_n:
        return 0.0
    if name_n in raw_n:
        return 1.0
    raw_tokens = set(raw_n.split())
    name_tokens = set(name_n.split())
    if not name_tokens:
        return 0.0
    overlap = raw_tokens & name_tokens
    containment = len(overlap) / len(name_tokens)
    jaccard = len(overlap) / max(1, len(raw_tokens | name_tokens))
    return 0.85 * containment + 0.15 * jaccard


def useful_affiliation_queries(raw: str) -> List[str]:
    raw = " ".join(str(raw or "").split())
    if not raw:
        return []

    queries = [raw]
    parts = [p.strip() for p in re.split(r"[;,|]", raw) if p.strip()]
    institution_words = (
        "university", "universitat", "universite", "università",
        "institute", "institut", "college", "school", "polytechnic",
        "polytechnique", "eth ", "epfl", "cnrs", "inria",
    )
    preferred = [
        p for p in parts if any(word in p.lower() for word in institution_words)
    ]
    queries.extend(preferred)
    for i in range(len(parts) - 1):
        joined = f"{parts[i]}, {parts[i+1]}"
        if any(word in joined.lower() for word in institution_words):
            queries.append(joined)

    return sorted(dict.fromkeys(queries), key=len, reverse=True)[:6]


def resolve_raw_affiliation(
    raw: str,
    cache: Dict[str, Optional[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    key = normalize(raw)
    if not key:
        return None
    if key in cache:
        return cache[key]

    best = None
    best_score = 0.0
    for query in useful_affiliation_queries(raw):
        data = request_json(
            openalex_url("institutions", {"search": query, "per-page": 7})
        )
        if not data:
            continue
        for candidate in data.get("results") or []:
            score = affiliation_match_score(
                raw, candidate.get("display_name") or ""
            )
            if score > best_score:
                best, best_score = candidate, score
        if best_score >= 0.95:
            break
        time.sleep(0.02)

    if best is None or best_score < RAW_AFFILIATION_MATCH_THRESHOLD:
        cache[key] = None
        return None

    cache[key] = best
    return best


def extract_arxiv_id(paper: Dict[str, Any]) -> str:
    # Search every simple value recursively by serializing the small paper object.
    haystack = json.dumps(paper, ensure_ascii=False)
    match = re.search(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", haystack)
    return match.group(1) if match else ""


def fallback_paper_for(
    paper: Dict[str, Any], fallback_papers: Dict[str, Any]
) -> Tuple[str, Optional[Dict[str, Any]]]:
    arxiv_id = extract_arxiv_id(paper)
    if arxiv_id and arxiv_id in fallback_papers:
        return arxiv_id, fallback_papers[arxiv_id]

    title_n = normalize(paper.get("title") or "")
    if title_n:
        for key, record in fallback_papers.items():
            if normalize(record.get("title") or "") == title_n:
                return key, record
    return "", None


def paper_record(
    paper: Dict[str, Any], coauthors: Iterable[str], evidence: Iterable[str]
) -> Dict[str, Any]:
    return {
        "id": paper.get("id") or "",
        "title": paper.get("title") or "",
        "year": paper.get("year"),
        "url": paper.get("url") or "",
        "coauthors": sorted({name for name in coauthors if name}),
        "evidence": sorted(set(evidence)),
    }


def main() -> int:
    publications = load_json(PUBLICATIONS_PATH, {})
    papers = [p for p in publications.get("papers", []) if p and p.get("title")]
    if not papers:
        print("No papers found in data/publications.json; preserving existing collaboration data.")
        return 0

    fallback = load_json(FALLBACK_PATH, {})
    fallback_papers = fallback.get("paper_affiliations", {}) or {}
    fallback_catalog = fallback.get("institution_catalog", {}) or {}
    current_fallback = fallback.get("current_affiliations", {}) or {}

    overrides = load_json(OVERRIDES_PATH, {})
    excluded_authors = {normalize(x) for x in overrides.get("exclude_authors", [])}
    excluded_institutions = {
        normalize(x) for x in overrides.get("exclude_institutions", [])
    }
    institution_overrides = overrides.get("institution_overrides", {}) or {}

    previous = load_json(OUTPUT_PATH, {})
    previous_by_name = {
        normalize(item.get("name")): item
        for item in previous.get("institutions", [])
        if item.get("name")
    }

    catalog_by_norm = {
        normalize(name): {"name": name, **geo}
        for name, geo in fallback_catalog.items()
    }

    aggregates: Dict[str, Dict[str, Any]] = {}
    known_coauthors = set()

    def ensure_institution(
        institution_name: str,
        *,
        geo: Optional[Dict[str, Any]] = None,
        openalex_id: str = "",
        source: str = "",
    ) -> Optional[str]:
        name = str(institution_name or "").strip()
        if not name or normalize(name) in excluded_institutions:
            return None

        key = normalize(name)
        catalog_hit = catalog_by_norm.get(key)
        if catalog_hit:
            name = catalog_hit["name"]
            key = normalize(name)

        if key not in aggregates:
            merged_geo = {}
            if catalog_hit:
                merged_geo.update(catalog_hit)
            if geo:
                source_geo = geo.get("geo") if isinstance(geo.get("geo"), dict) else geo
                merged_geo.update({
                    "city": source_geo.get("city") or merged_geo.get("city") or "",
                    "region": source_geo.get("region") or merged_geo.get("region") or "",
                    "country": source_geo.get("country") or merged_geo.get("country") or "",
                    "country_code": source_geo.get("country_code") or geo.get("country_code") or merged_geo.get("country_code") or "",
                    "latitude": source_geo.get("latitude", merged_geo.get("latitude")),
                    "longitude": source_geo.get("longitude", merged_geo.get("longitude")),
                })

            aggregates[key] = {
                "id": f"inst:{slug(name)}",
                "openalex_id": openalex_id or "",
                "name": name,
                "city": merged_geo.get("city") or "",
                "region": merged_geo.get("region") or "",
                "country": merged_geo.get("country") or "",
                "country_code": merged_geo.get("country_code") or "",
                "latitude": merged_geo.get("latitude"),
                "longitude": merged_geo.get("longitude"),
                "coauthors": set(),
                "current_coauthors": set(),
                "papers": {},
                "sources": set(),
                "current_sources": [],
            }
        else:
            if openalex_id and not aggregates[key]["openalex_id"]:
                aggregates[key]["openalex_id"] = openalex_id
            if geo:
                source_geo = geo.get("geo") if isinstance(geo.get("geo"), dict) else geo
                for field in ("city", "region", "country", "country_code", "latitude", "longitude"):
                    value = source_geo.get(field)
                    if value not in (None, "") and aggregates[key].get(field) in (None, ""):
                        aggregates[key][field] = value

        if source:
            aggregates[key]["sources"].add(source)
        return key

    author_id = resolve_author_id()
    author_works = fetch_author_works(author_id) if author_id else []
    openalex_available = bool(author_id and author_works)

    unmatched: List[Dict[str, Any]] = []
    matched_count = 0
    papers_with_affiliations = set()
    raw_resolved_count = 0
    raw_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    match_methods: Dict[str, int] = {}
    fallback_paper_links_added = 0
    fallback_papers_used = set()

    for paper in papers:
        paper_key = paper.get("id") or normalize(paper.get("title"))
        paper_institutions: Dict[str, set] = {}
        paper_evidence: Dict[str, set] = {}

        work, score, method = match_work(paper, author_works, author_id)
        if work:
            matched_count += 1
            match_methods[method] = match_methods.get(method, 0) + 1

            for authorship in work.get("authorships") or []:
                if is_self_authorship(authorship, author_id):
                    continue

                author = authorship.get("author") or {}
                author_name = (
                    author.get("display_name")
                    or authorship.get("raw_author_name")
                    or "Unknown co-author"
                )
                if normalize(author_name) in excluded_authors:
                    continue

                known_coauthors.add(normalize(author_name))
                resolved_this_authorship = set()

                for inst in authorship.get("institutions") or []:
                    inst_name = inst.get("display_name") or ""
                    inst_key = ensure_institution(
                        inst_name,
                        geo=inst,
                        openalex_id=str(inst.get("id") or ""),
                        source="openalex-structured",
                    )
                    if inst_key:
                        aggregates[inst_key]["coauthors"].add(author_name)
                        paper_institutions.setdefault(inst_key, set()).add(author_name)
                        paper_evidence.setdefault(inst_key, set()).add("openalex-structured")
                        resolved_this_authorship.add(inst_key)

                for raw in raw_affiliation_strings(authorship):
                    resolved = resolve_raw_affiliation(raw, raw_cache)
                    if not resolved:
                        continue
                    inst_key = ensure_institution(
                        resolved.get("display_name") or "",
                        geo=resolved,
                        openalex_id=str(resolved.get("id") or ""),
                        source="openalex-raw-affiliation",
                    )
                    if inst_key:
                        aggregates[inst_key]["coauthors"].add(author_name)
                        paper_institutions.setdefault(inst_key, set()).add(author_name)
                        paper_evidence.setdefault(inst_key, set()).add("openalex-raw-affiliation")
                        if inst_key not in resolved_this_authorship:
                            raw_resolved_count += 1
                        resolved_this_authorship.add(inst_key)
        else:
            unmatched.append({
                "id": paper.get("id") or "",
                "title": paper.get("title") or "",
                "year": paper.get("year"),
                "best_title_match_score": round(float(score), 3),
                "openalex_status": method,
            })

        # Curated exact-paper fallback. It supplements OpenAlex; it does not overwrite it.
        arxiv_id, curated = fallback_paper_for(paper, fallback_papers)
        if curated and curated.get("status") != "single_author":
            used_this_paper = False
            for author_name, institution_names in (curated.get("coauthors") or {}).items():
                if normalize(author_name) in excluded_authors:
                    continue
                known_coauthors.add(normalize(author_name))

                for institution_name in institution_names or []:
                    inst_key = ensure_institution(
                        institution_name,
                        source="curated-arxiv-fallback",
                    )
                    if not inst_key:
                        continue

                    was_present = author_name in paper_institutions.get(inst_key, set())
                    aggregates[inst_key]["coauthors"].add(author_name)
                    paper_institutions.setdefault(inst_key, set()).add(author_name)
                    paper_evidence.setdefault(inst_key, set()).add("curated-arxiv-fallback")
                    if not was_present:
                        fallback_paper_links_added += 1
                    used_this_paper = True

            if used_this_paper:
                fallback_papers_used.add(arxiv_id or normalize(curated.get("title") or ""))

        if paper_institutions:
            papers_with_affiliations.add(paper_key)

        for inst_key, coauthors in paper_institutions.items():
            aggregates[inst_key]["papers"][paper_key] = paper_record(
                paper,
                coauthors,
                paper_evidence.get(inst_key, set()),
            )

    # Current affiliations are *display metadata only*. Never count them as paper affiliations.
    current_people_added = set()
    for person_name, records in current_fallback.items():
        if normalize(person_name) not in known_coauthors:
            continue
        for record in records or []:
            institution_name = record.get("institution") or ""
            inst_key = ensure_institution(
                institution_name,
                source="current-affiliation-fallback",
            )
            if not inst_key:
                continue
            aggregates[inst_key]["current_coauthors"].add(person_name)
            aggregates[inst_key]["current_sources"].append({
                "person": person_name,
                "source_type": record.get("source_type") or "",
                "source_url": record.get("source_url") or "",
                "secondary_url": record.get("secondary_url") or "",
                "verified_at": record.get("verified_at") or "",
                "confidence": record.get("confidence") or "",
                "note": record.get("note") or "",
            })
            current_people_added.add(normalize(person_name))

    # Fill any remaining geo gaps using last successful output, OpenAlex, then curated city-level coordinates.
    for key, aggregate in aggregates.items():
        prev = previous_by_name.get(normalize(aggregate["name"]), {})
        for field in ("city", "region", "country", "country_code", "latitude", "longitude"):
            if aggregate.get(field) in (None, "") and prev.get(field) not in (None, ""):
                aggregate[field] = prev.get(field)

        if (aggregate.get("latitude") is None or aggregate.get("longitude") is None) and aggregate.get("openalex_id"):
            full = fetch_institution(aggregate["openalex_id"])
            time.sleep(0.02)
            if full:
                source_geo = full.get("geo") or {}
                for field in ("city", "region", "country", "country_code", "latitude", "longitude"):
                    value = source_geo.get(field) or (full.get(field) if field == "country_code" else None)
                    if value not in (None, "") and aggregate.get(field) in (None, ""):
                        aggregate[field] = value

        catalog_hit = catalog_by_norm.get(normalize(aggregate["name"]))
        if catalog_hit:
            for field in ("city", "region", "country", "country_code", "latitude", "longitude"):
                if aggregate.get(field) in (None, "") and catalog_hit.get(field) not in (None, ""):
                    aggregate[field] = catalog_hit[field]

        override = (
            institution_overrides.get(aggregate.get("openalex_id") or "")
            or institution_overrides.get(strip_openalex_id(aggregate.get("openalex_id") or ""))
            or institution_overrides.get(normalize(aggregate["name"]))
            or {}
        )
        for field in ("name", "city", "region", "country", "country_code", "latitude", "longitude"):
            if field in override:
                aggregate[field] = override[field]

    institutions: List[Dict[str, Any]] = []
    for key, aggregate in sorted(aggregates.items(), key=lambda kv: normalize(kv[1]["name"])):
        try:
            latitude = float(aggregate["latitude"])
            longitude = float(aggregate["longitude"])
        except (TypeError, ValueError):
            continue

        papers_out = list(aggregate["papers"].values())
        papers_out.sort(
            key=lambda p: (-(int(p["year"] or 0)), normalize(p["title"]))
        )

        institutions.append({
            "id": aggregate["id"],
            "openalex_id": aggregate.get("openalex_id") or "",
            "name": aggregate["name"],
            "city": aggregate.get("city") or "",
            "region": aggregate.get("region") or "",
            "country": aggregate.get("country") or "",
            "country_code": aggregate.get("country_code") or "",
            "latitude": latitude,
            "longitude": longitude,
            "coauthors": sorted(aggregate["coauthors"]),
            "current_coauthors": sorted(aggregate["current_coauthors"]),
            "paper_count": len(papers_out),
            "papers": papers_out,
            "has_historical": bool(papers_out),
            "has_current": bool(aggregate["current_coauthors"]),
            "sources": sorted(aggregate["sources"]),
            "current_sources": aggregate["current_sources"],
        })

    output = {
        "generated_at": now_iso(),
        "source": (
            "OpenAlex structured/raw paper affiliations + curated arXiv paper-version "
            "fallback + separately tracked current LinkedIn/official affiliations"
        ),
        "author": {
            "name": AUTHOR_NAME,
            "openalex_id": f"https://openalex.org/{author_id}" if author_id else "",
        },
        "openalex_available": openalex_available,
        "matched_publications": matched_count,
        "publications_with_resolved_affiliations": len(papers_with_affiliations),
        "total_publications": len(papers),
        "raw_affiliations_resolved": raw_resolved_count,
        "fallback_paper_links_added": fallback_paper_links_added,
        "fallback_papers_used": len(fallback_papers_used),
        "current_affiliation_people": len(current_people_added),
        "match_methods": match_methods,
        "institutions": institutions,
        "unmatched_publications": unmatched,
    }

    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    historical_institutions = sum(1 for x in institutions if x["has_historical"])
    current_institutions = sum(1 for x in institutions if x["has_current"])
    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with "
        f"{historical_institutions} historical institutions and "
        f"{current_institutions} current-affiliation institutions; "
        f"{len(papers_with_affiliations)}/{len(papers)} papers have resolved "
        f"co-author affiliations; {fallback_paper_links_added} curated "
        f"paper-affiliation links added; {len(current_people_added)} current "
        f"coauthor profiles added."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
