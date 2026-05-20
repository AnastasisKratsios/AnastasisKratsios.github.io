#!/usr/bin/env python3
"""Refresh data/talks.json from the Fields Mathematical AI Seminar page.

The script is intentionally fail-safe: if the Fields page changes or blocks a
run, the previous talks.json is kept so the website still renders.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "talks.json"
SOURCE_URL = os.environ.get("FIELDS_MATHAI_URL", "https://www.fields.utoronto.ca/activities/25-26/mathai")
FALLBACK_SOURCE_URLS = [
    SOURCE_URL,
    SOURCE_URL.replace("https://www.fields.utoronto.ca", "https://www2.fields.utoronto.ca"),
    SOURCE_URL.replace("https://", "http://"),
]
USER_AGENT = os.environ.get("FIELDS_TALK_UPDATER_USER_AGENT", "AnastasisKratsios.github.io Fields seminar updater")
REQUIRE_SUCCESS = os.environ.get("REQUIRE_SUCCESS", "0") == "1"
MAX_TALKS = int(os.environ.get("MAX_FIELDS_TALKS", "12"))


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def text_of(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True) if node else "").strip()


def fetch(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=35, allow_redirects=True)
        if resp.ok and resp.text:
            return resp.text
    except Exception as exc:
        print(f"Could not fetch {url}: {exc}")
    return None


def first_page() -> tuple[str, str]:
    for url in FALLBACK_SOURCE_URLS:
        html = fetch(url)
        if html:
            return html, url
    raise RuntimeError("Could not fetch Fields Mathematical AI Seminar page.")


def talk_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/talks/" in href:
            links.append(urljoin(base_url, href))
    # Prefer exact Fields talk pages, keep order, deduplicate.
    deduped = []
    seen = set()
    for link in links:
        clean = link.split("#")[0]
        if clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    return deduped


def after_label(text: str, label: str) -> str:
    pat = re.compile(re.escape(label) + r"\s*:?\s*(.*?)(?=\s+(Speaker|Date and Time|Location|Abstract|Bio|Scheduled as part of):?\s*|$)", re.I | re.S)
    m = pat.search(text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def parse_iso(date_text: str) -> str:
    # Keep this conservative; the display string remains authoritative.
    m = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4}).*?(\d{1,2}):(\d{2})(am|pm)", date_text, re.I)
    if not m:
        return ""
    month = dt.datetime.strptime(m.group(2)[:3], "%b").month
    day = int(m.group(3)); year = int(m.group(4)); hour = int(m.group(5)); minute = int(m.group(6))
    if m.group(7).lower() == "pm" and hour != 12: hour += 12
    if m.group(7).lower() == "am" and hour == 12: hour = 0
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00-04:00"


def parse_talk(url: str) -> Optional[Dict[str, Any]]:
    html = fetch(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    title = text_of(soup.find("h1"))
    body = text_of(soup)
    if not title or "Mathematical AI Seminar" not in body:
        return None
    speaker = after_label(body, "Speaker")
    date = after_label(body, "Date and Time")
    location = after_label(body, "Location")
    return {
        "title": title,
        "speaker": speaker,
        "date": date,
        "date_iso": parse_iso(date),
        "location": location,
        "url": url,
    }


def preserve(reason: str) -> int:
    print(f"Talk refresh failed: {reason}")
    if REQUIRE_SUCCESS:
        return 1
    if DATA_PATH.exists():
        print("Preserving existing data/talks.json.")
        return 0
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps({"generated_at": now_iso(), "source_url": SOURCE_URL, "talks": []}, indent=2) + "\n")
    return 0


def main() -> int:
    try:
        html, source = first_page()
        links = talk_links(html, source)
        talks = []
        for link in links[:MAX_TALKS * 3]:
            t = parse_talk(link)
            if t:
                talks.append(t)
            if len(talks) >= MAX_TALKS:
                break
        if not talks:
            return preserve("no talks parsed from Fields page")
        talks.sort(key=lambda t: t.get("date_iso") or t.get("date") or "", reverse=True)
        data = {
            "generated_at": now_iso(),
            "source_url": source,
            "source": "Fields Institute Mathematical AI Seminar page",
            "talks": talks,
        }
        DATA_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(talks)} talks to {DATA_PATH}")
        return 0
    except Exception as exc:
        return preserve(repr(exc))


if __name__ == "__main__":
    raise SystemExit(main())
