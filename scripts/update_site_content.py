#!/usr/bin/env python3
"""Refresh auxiliary website content.

This currently refreshes data/upcoming_talks.json from the Fields Institute
Mathematical AI Seminar page.  The script is intentionally fail-safe: if the
Fields page layout changes or blocks a request, the existing JSON is preserved
so GitHub Pages keeps serving the last successful version.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
TALKS_PATH = ROOT / "data" / "upcoming_talks.json"
FIELDS_MATHAI_URL = os.environ.get("FIELDS_MATHAI_URL", "https://www.fields.utoronto.ca/activities/25-26/mathai")
USER_AGENT = os.environ.get(
    "PUBLICATION_UPDATER_USER_AGENT",
    "AnastasisKratsios.github.io site content updater (mailto:kratsiosanastasis@gmail.com)",
)
REQUIRE_SUCCESS = os.environ.get("REQUIRE_SUCCESS", "0") == "1"

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sept\.?|Sep\.?|Oct\.?|Nov\.?|Dec\. ?"
DATE_RE = re.compile(rf"\b(?:{MONTHS})\s+\d{{1,2}}(?:,\s*\d{{4}})?\b|\b\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}\b", re.I)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)?\b")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def fetch_fields_html() -> str:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(FIELDS_MATHAI_URL, headers=headers, timeout=45, allow_redirects=True)
    if not resp.ok:
        raise RuntimeError(f"Fields page returned HTTP {resp.status_code}")
    return resp.text


def extract_date(text: str) -> str:
    m = DATE_RE.search(text or "")
    return clean(m.group(0)) if m else ""


def extract_time(text: str) -> str:
    m = TIME_RE.search(text or "")
    return clean(m.group(0)) if m else ""


def likely_talk_text(text: str) -> bool:
    if len(text) < 18 or len(text) > 1200:
        return False
    low = text.lower()
    bad = ["skip to", "menu", "search", "footer", "facebook", "twitter", "youtube", "contact", "subscribe"]
    if any(b in low for b in bad):
        return False
    return bool(DATE_RE.search(text) or "speaker" in low or "abstract" in low or "title" in low)


def split_speaker_title(text: str) -> Dict[str, str]:
    text = clean(text)
    # Common Fields/event patterns: "Date Speaker Title" or explicit labels.
    speaker = ""
    title = ""
    speaker_match = re.search(r"Speaker\s*:?\s*([^|]+?)(?:Title|Abstract|$)", text, re.I)
    if speaker_match:
        speaker = clean(speaker_match.group(1))
    title_match = re.search(r"Title\s*(?:and\s*Abstract)?\s*:?\s*([^|]+?)(?:Abstract|Speaker|$)", text, re.I)
    if title_match:
        title = clean(title_match.group(1))

    if not title:
        # Remove date/time and site boilerplate, then keep the informative tail.
        stripped = DATE_RE.sub("", text)
        stripped = TIME_RE.sub("", stripped)
        stripped = re.sub(r"\b(Mathematical AI Seminar|Fields Institute|The Fields Institute)\b", "", stripped, flags=re.I)
        parts = [clean(x) for x in re.split(r"\s[-–—]\s|\s\|\s", stripped) if clean(x)]
        if parts:
            if not speaker and len(parts) >= 2:
                speaker = parts[0]
                title = parts[1]
            else:
                title = parts[-1]
    return {"speaker": speaker[:180], "title": title[:260]}


def parse_talks(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    selectors = [".views-row", "article", ".node", ".event", "tr", "li"]
    seen_texts = set()
    for selector in selectors:
        for elem in soup.select(selector):
            text = clean(elem.get_text(" "))
            key = text.lower()[:240]
            if key in seen_texts or not likely_talk_text(text):
                continue
            seen_texts.add(key)
            link = elem.find("a", href=True)
            url = urljoin(FIELDS_MATHAI_URL, link["href"]) if link else FIELDS_MATHAI_URL
            date = extract_date(text)
            time = extract_time(text)
            parsed = split_speaker_title(text)
            title = parsed["title"]
            speaker = parsed["speaker"]
            if title or speaker or date:
                candidates.append({
                    "date": date,
                    "time": time,
                    "speaker": speaker,
                    "title": title,
                    "url": url,
                    "raw": text[:500],
                })

    # De-duplicate by date/speaker/title/url, preserving page order.
    out = []
    seen = set()
    for t in candidates:
        key = (t.get("date", "").lower(), t.get("speaker", "").lower(), t.get("title", "").lower(), t.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out[:12]


def write_talks(talks: List[Dict[str, Any]]) -> None:
    TALKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": now_iso(),
        "source": "Fields Institute Mathematical AI Seminar page",
        "fields_url": FIELDS_MATHAI_URL,
        "talks": talks,
    }
    TALKS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(talks)} talks to {TALKS_PATH}")


def preserve_existing(reason: str) -> int:
    print(f"Talk refresh failed: {reason}", file=sys.stderr)
    if REQUIRE_SUCCESS:
        return 1
    if TALKS_PATH.exists():
        print("Preserving existing data/upcoming_talks.json.")
        return 0
    write_talks([])
    return 0


def main() -> int:
    try:
        html = fetch_fields_html()
        talks = parse_talks(html)
        write_talks(talks)
        return 0
    except Exception as exc:
        return preserve_existing(repr(exc))


if __name__ == "__main__":
    raise SystemExit(main())
