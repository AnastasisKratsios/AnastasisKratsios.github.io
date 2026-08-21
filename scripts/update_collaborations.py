#!/usr/bin/env python3
"""Build data/collaborations.json from the site's existing publication metadata.

The script is deliberately separate from update_publications.py so the existing
publication pipeline remains untouched.

Source of truth:
- data/publications.json decides which papers belong on the site.
- OpenAlex supplies paper-level authorships and the institutions listed for each
  author on each work.
- OpenAlex institution records supply map coordinates.

If OpenAlex is temporarily unavailable, an existing collaborations.json is
preserved rather than replaced with broken/empty data.
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
OPENALEX_MAILTO = os.environ.get("OPENALEX_MAILTO", "kratsiosanastasis@gmail.com").strip()
USER_AGENT = os.environ.get(
    "COLLABORATION_MAP_USER_AGENT",
    "AnastasisKratsios.github.io collaboration map updater",
)

TITLE_MATCH_THRESHOLD = float(os.environ.get("COLLABORATION_TITLE_MATCH_THRESHOLD", "0.78"))
MAX_OPENALEX_WORKS = int(os.environ.get("MAX_OPENALEX_WORKS", "500"))


def normalize(text: Any) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    exact = [item for item in results if normalize(item.get("display_name")) == target]
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


def match_work(paper: Dict[str, Any], works: Iterable[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
    title = paper.get("title") or ""
    year = paper.get("year")
    doi = normalize(str(paper.get("doi") or "").replace("https://doi.org/", ""))

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0

    for work in works:
        if doi:
            work_doi = normalize(str(work.get("doi") or "").replace("https://doi.org/", ""))
            if work_doi and work_doi == doi:
                return work, 1.0

        score = title_similarity(title, work.get("display_name") or "")
        work_year = work.get("publication_year")
        if year and work_year:
            try:
                delta = abs(int(year) - int(work_year))
                if delta == 0:
                    score += 0.03
                elif delta > 2:
                    score -= 0.08
            except Exception:
                pass

        if score > best_score:
            best, best_score = work, score

    return (best, min(best_score, 1.0)) if best_score >= TITLE_MATCH_THRESHOLD else (None, best_score)


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


def paper_record(paper: Dict[str, Any], coauthors: Iterable[str]) -> Dict[str, Any]:
    return {
        "id": paper.get("id") or "",
        "title": paper.get("title") or "",
        "year": paper.get("year"),
        "url": paper.get("url") or "",
        "coauthors": sorted({name for name in coauthors if name}),
    }


def main() -> int:
    publications = load_json(PUBLICATIONS_PATH, {})
    papers = [p for p in publications.get("papers", []) if p and p.get("title")]
    if not papers:
        print("No papers found in data/publications.json; preserving existing collaboration data.")
        return 0

    author_id = resolve_author_id()
    if not author_id:
        print("Could not resolve OpenAlex author ID; preserving existing collaboration data.")
        return 0

    works = fetch_author_works(author_id)
    if not works:
        print("Could not load OpenAlex works; preserving existing collaboration data.")
        return 0

    overrides = load_json(OVERRIDES_PATH, {})
    excluded_authors = {normalize(x) for x in overrides.get("exclude_authors", [])}
    excluded_institutions = {normalize(x) for x in overrides.get("exclude_institutions", [])}
    institution_overrides = overrides.get("institution_overrides", {}) or {}

    previous = load_json(OUTPUT_PATH, {})
    previous_by_id = {
        str(item.get("id") or ""): item
        for item in previous.get("institutions", [])
        if item.get("id")
    }

    # institution_id -> aggregate
    aggregates: Dict[str, Dict[str, Any]] = {}
    unmatched: List[Dict[str, Any]] = []
    matched_count = 0

    for paper in papers:
        work, score = match_work(paper, works)
        if not work:
            unmatched.append({
                "id": paper.get("id") or "",
                "title": paper.get("title") or "",
                "year": paper.get("year"),
                "best_title_match_score": round(float(score), 3),
            })
            continue

        matched_count += 1
        paper_institutions: Dict[str, set] = {}

        for authorship in work.get("authorships") or []:
            if is_self_authorship(authorship, author_id):
                continue

            author = authorship.get("author") or {}
            author_name = author.get("display_name") or authorship.get("raw_author_name") or "Unknown co-author"
            if normalize(author_name) in excluded_authors:
                continue

            for inst in authorship.get("institutions") or []:
                institution_id = str(inst.get("id") or "")
                institution_name = inst.get("display_name") or ""
                if not institution_id or not institution_name:
                    continue
                if normalize(institution_name) in excluded_institutions:
                    continue

                paper_institutions.setdefault(institution_id, set()).add(author_name)
                if institution_id not in aggregates:
                    aggregates[institution_id] = {
                        "id": institution_id,
                        "name": institution_name,
                        "country_code": inst.get("country_code") or "",
                        "coauthors": set(),
                        "papers": {},
                    }

                aggregates[institution_id]["coauthors"].add(author_name)

        for institution_id, coauthors in paper_institutions.items():
            aggregates[institution_id]["papers"][paper.get("id") or normalize(paper.get("title"))] = paper_record(
                paper, coauthors
            )

    institutions: List[Dict[str, Any]] = []

    for institution_id, aggregate in sorted(aggregates.items(), key=lambda kv: normalize(kv[1]["name"])):
        cached = previous_by_id.get(institution_id, {})
        geo = {
            "city": cached.get("city") or "",
            "region": cached.get("region") or "",
            "country": cached.get("country") or "",
            "country_code": cached.get("country_code") or aggregate.get("country_code") or "",
            "latitude": cached.get("latitude"),
            "longitude": cached.get("longitude"),
        }

        if geo["latitude"] is None or geo["longitude"] is None:
            full = fetch_institution(institution_id)
            time.sleep(0.03)
            if full:
                source_geo = full.get("geo") or {}
                aggregate["name"] = full.get("display_name") or aggregate["name"]
                geo.update({
                    "city": source_geo.get("city") or "",
                    "region": source_geo.get("region") or "",
                    "country": source_geo.get("country") or "",
                    "country_code": source_geo.get("country_code") or full.get("country_code") or geo["country_code"],
                    "latitude": source_geo.get("latitude"),
                    "longitude": source_geo.get("longitude"),
                })

        # Overrides may be keyed by OpenAlex ID, full URL, or normalized institution name.
        override = (
            institution_overrides.get(institution_id)
            or institution_overrides.get(strip_openalex_id(institution_id))
            or institution_overrides.get(normalize(aggregate["name"]))
            or {}
        )
        for key in ("name", "city", "region", "country", "country_code", "latitude", "longitude"):
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
        papers_out.sort(key=lambda p: (-(int(p["year"] or 0)), normalize(p["title"])))

        institutions.append({
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
        })

    output = {
        "generated_at": now_iso(),
        "source": "OpenAlex paper-level authorships matched to data/publications.json",
        "author": {
            "name": AUTHOR_NAME,
            "openalex_id": f"https://openalex.org/{author_id}",
        },
        "matched_publications": matched_count,
        "total_publications": len(papers),
        "institutions": institutions,
        "unmatched_publications": unmatched,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with "
        f"{len(institutions)} institutions from {matched_count}/{len(papers)} matched publications."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
