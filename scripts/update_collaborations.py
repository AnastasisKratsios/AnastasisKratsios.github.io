#!/usr/bin/env python3
"""Build data/collaborations.json from the site's existing publication metadata.

Version 2 is intentionally conservative but substantially more complete:
1. Match each site publication to an OpenAlex work.
2. Use OpenAlex's structured paper-level author institutions when available.
3. If an authorship has no structured institution, resolve that authorship's
   raw affiliation string(s) from the SAME paper to an OpenAlex institution.
4. For site papers missing from the target author's OpenAlex profile, fall back
   to a title search and require the target author to be present.

The browser still reads only data/collaborations.json; this script does all API
work during the scheduled GitHub Action.
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
    doi = normalize(
        str(paper.get("doi") or "").replace("https://doi.org/", "")
    )
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
    author_id: str,
) -> Tuple[Optional[Dict[str, Any]], float, str]:
    work, score = match_work_from_pool(paper, author_works)
    if work:
        return work, score, "author-profile"

    work, search_score = search_work_by_title(paper, author_id)
    if work:
        return work, search_score, "title-search"

    return None, max(score, search_score), "unmatched"


def is_self_authorship(authorship: Dict[str, Any], author_id: str) -> bool:
    author = authorship.get("author") or {}
    if strip_openalex_id(author.get("id")) == author_id:
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
    """Generate a few conservative search strings from a paper affiliation line."""
    raw = " ".join(str(raw or "").split())
    if not raw:
        return []

    queries = [raw]
    parts = [
        p.strip()
        for p in re.split(r"[;,|]", raw)
        if p.strip()
    ]

    institution_words = (
        "university",
        "universitat",
        "universite",
        "università",
        "institute",
        "institut",
        "college",
        "school",
        "polytechnic",
        "polytechnique",
        "eth ",
        "epfl",
        "cnrs",
        "inria",
    )

    preferred = [
        p for p in parts
        if any(word in p.lower() for word in institution_words)
    ]
    queries.extend(preferred)

    # Occasionally the institution spans two comma-separated pieces.
    for i in range(len(parts) - 1):
        joined = f"{parts[i]}, {parts[i+1]}"
        if any(word in joined.lower() for word in institution_words):
            queries.append(joined)

    # Longest institution-looking strings first, no duplicates.
    return sorted(
        dict.fromkeys(queries),
        key=len,
        reverse=True,
    )[:6]


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
            openalex_url(
                "institutions",
                {
                    "search": query,
                    "per-page": 7,
                },
            )
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


def add_institution(
    aggregates: Dict[str, Dict[str, Any]],
    inst: Dict[str, Any],
    author_name: str,
    excluded_institutions: set,
) -> Optional[str]:
    institution_id = str(inst.get("id") or "")
    institution_name = inst.get("display_name") or ""
    if not institution_id or not institution_name:
        return None
    if normalize(institution_name) in excluded_institutions:
        return None

    if institution_id not in aggregates:
        geo = inst.get("geo") or {}
        aggregates[institution_id] = {
            "id": institution_id,
            "name": institution_name,
            "country_code": (
                inst.get("country_code")
                or geo.get("country_code")
                or ""
            ),
            "coauthors": set(),
            "papers": {},
        }

    aggregates[institution_id]["coauthors"].add(author_name)
    return institution_id


def paper_record(
    paper: Dict[str, Any], coauthors: Iterable[str]
) -> Dict[str, Any]:
    return {
        "id": paper.get("id") or "",
        "title": paper.get("title") or "",
        "year": paper.get("year"),
        "url": paper.get("url") or "",
        "coauthors": sorted({name for name in coauthors if name}),
    }


def main() -> int:
    publications = load_json(PUBLICATIONS_PATH, {})
    papers = [
        p for p in publications.get("papers", [])
        if p and p.get("title")
    ]
    if not papers:
        print(
            "No papers found in data/publications.json; "
            "preserving existing collaboration data."
        )
        return 0

    author_id = resolve_author_id()
    if not author_id:
        print(
            "Could not resolve OpenAlex author ID; "
            "preserving existing collaboration data."
        )
        return 0

    author_works = fetch_author_works(author_id)
    if not author_works:
        print(
            "Could not load OpenAlex works; "
            "preserving existing collaboration data."
        )
        return 0

    overrides = load_json(OVERRIDES_PATH, {})
    excluded_authors = {
        normalize(x) for x in overrides.get("exclude_authors", [])
    }
    excluded_institutions = {
        normalize(x)
        for x in overrides.get("exclude_institutions", [])
    }
    institution_overrides = (
        overrides.get("institution_overrides", {}) or {}
    )

    previous = load_json(OUTPUT_PATH, {})
    previous_by_id = {
        str(item.get("id") or ""): item
        for item in previous.get("institutions", [])
        if item.get("id")
    }

    aggregates: Dict[str, Dict[str, Any]] = {}
    unmatched: List[Dict[str, Any]] = []
    matched_count = 0
    papers_with_affiliations = set()
    raw_resolved_count = 0
    raw_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    match_methods: Dict[str, int] = {}

    for paper in papers:
        work, score, method = match_work(
            paper, author_works, author_id
        )
        if not work:
            unmatched.append(
                {
                    "id": paper.get("id") or "",
                    "title": paper.get("title") or "",
                    "year": paper.get("year"),
                    "best_title_match_score": round(float(score), 3),
                }
            )
            continue

        matched_count += 1
        match_methods[method] = match_methods.get(method, 0) + 1

        # institution_id -> coauthors on THIS paper
        paper_institutions: Dict[str, set] = {}

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

            resolved_this_authorship = set()

            # First choice: OpenAlex's structured paper-level affiliations.
            for inst in authorship.get("institutions") or []:
                institution_id = add_institution(
                    aggregates,
                    inst,
                    author_name,
                    excluded_institutions,
                )
                if institution_id:
                    resolved_this_authorship.add(institution_id)
                    paper_institutions.setdefault(
                        institution_id, set()
                    ).add(author_name)

            # Fallback / supplement: raw affiliation text printed on this paper.
            for raw in raw_affiliation_strings(authorship):
                resolved = resolve_raw_affiliation(raw, raw_cache)
                if not resolved:
                    continue

                institution_id = add_institution(
                    aggregates,
                    resolved,
                    author_name,
                    excluded_institutions,
                )
                if institution_id:
                    if institution_id not in resolved_this_authorship:
                        raw_resolved_count += 1
                    resolved_this_authorship.add(institution_id)
                    paper_institutions.setdefault(
                        institution_id, set()
                    ).add(author_name)

        if paper_institutions:
            papers_with_affiliations.add(
                paper.get("id") or normalize(paper.get("title"))
            )

        for institution_id, coauthors in paper_institutions.items():
            aggregates[institution_id]["papers"][
                paper.get("id") or normalize(paper.get("title"))
            ] = paper_record(paper, coauthors)

    institutions: List[Dict[str, Any]] = []

    for institution_id, aggregate in sorted(
        aggregates.items(),
        key=lambda kv: normalize(kv[1]["name"]),
    ):
        cached = previous_by_id.get(institution_id, {})
        geo = {
            "city": cached.get("city") or "",
            "region": cached.get("region") or "",
            "country": cached.get("country") or "",
            "country_code": (
                cached.get("country_code")
                or aggregate.get("country_code")
                or ""
            ),
            "latitude": cached.get("latitude"),
            "longitude": cached.get("longitude"),
        }

        if geo["latitude"] is None or geo["longitude"] is None:
            full = fetch_institution(institution_id)
            time.sleep(0.02)
            if full:
                source_geo = full.get("geo") or {}
                aggregate["name"] = (
                    full.get("display_name") or aggregate["name"]
                )
                geo.update(
                    {
                        "city": source_geo.get("city") or "",
                        "region": source_geo.get("region") or "",
                        "country": source_geo.get("country") or "",
                        "country_code": (
                            source_geo.get("country_code")
                            or full.get("country_code")
                            or geo["country_code"]
                        ),
                        "latitude": source_geo.get("latitude"),
                        "longitude": source_geo.get("longitude"),
                    }
                )

        override = (
            institution_overrides.get(institution_id)
            or institution_overrides.get(
                strip_openalex_id(institution_id)
            )
            or institution_overrides.get(
                normalize(aggregate["name"])
            )
            or {}
        )

        for key in (
            "name",
            "city",
            "region",
            "country",
            "country_code",
            "latitude",
            "longitude",
        ):
            if key in override:
                if key == "name":
                    aggregate["name"] = override[key]
                else:
                    geo[key] = override[key]

        try:
            latitude = float(geo["latitude"])
            longitude = float(geo["longitude"])
        except (TypeError, ValueError):
            continue

        papers_out = list(aggregate["papers"].values())
        papers_out.sort(
            key=lambda p: (
                -(int(p["year"] or 0)),
                normalize(p["title"]),
            )
        )

        institutions.append(
            {
                "id": institution_id,
                "name": aggregate["name"],
                "city": geo["city"],
                "region": geo["region"],
                "country": geo["country"],
                "country_code": geo["country_code"],
                "latitude": latitude,
                "longitude": longitude,
                "coauthors": sorted(aggregate["coauthors"]),
                "paper_count": len(papers_out),
                "papers": papers_out,
            }
        )

    output = {
        "generated_at": now_iso(),
        "source": (
            "OpenAlex structured paper-level authorships plus "
            "raw paper-affiliation fallback"
        ),
        "author": {
            "name": AUTHOR_NAME,
            "openalex_id": f"https://openalex.org/{author_id}",
        },
        "matched_publications": matched_count,
        "publications_with_resolved_affiliations": len(
            papers_with_affiliations
        ),
        "total_publications": len(papers),
        "raw_affiliations_resolved": raw_resolved_count,
        "match_methods": match_methods,
        "institutions": institutions,
        "unmatched_publications": unmatched,
    }

    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with "
        f"{len(institutions)} institutions; "
        f"{len(papers_with_affiliations)}/{len(papers)} papers have "
        f"resolved co-author affiliations; "
        f"{matched_count}/{len(papers)} papers matched to OpenAlex; "
        f"{raw_resolved_count} affiliation links recovered from raw text."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
