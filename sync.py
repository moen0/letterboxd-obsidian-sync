#!/usr/bin/env python3
"""
Letterboxd -> Obsidian Sync

Imports movies from Letterboxd into Obsidian as markdown notes with
YAML frontmatter properties and poster images.

Supports two modes:
  --bulk <path-to-diary.csv>   Import full history from Letterboxd CSV export
  --rss                        Sync latest entries from RSS feed (last 50)

Requires a free TMDB API key for movie metadata (director, genre, runtime, poster).
"""

import argparse
import csv
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
LETTERBOXD_USERNAME = os.getenv("LETTERBOXD_USERNAME", "Moneykriss")
OBSIDIAN_VAULT = os.getenv(
    "OBSIDIAN_VAULT_PATH",
    "/Users/kristoffermoen/Documents/Obsidian Vault Kristoffer/Kristoffer",
)
MOVIE_FOLDER = os.getenv("MOVIE_FOLDER", "LetterboxdDiary")
POSTER_FOLDER = os.getenv("POSTER_FOLDER", "posters")

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"

MOVIES_DIR = Path(OBSIDIAN_VAULT) / MOVIE_FOLDER
POSTERS_DIR = MOVIES_DIR / POSTER_FOLDER

RSS_URL = f"https://letterboxd.com/{LETTERBOXD_USERNAME}/rss/"

# Namespaces used in the Letterboxd RSS feed
NS = {
    "letterboxd": "https://letterboxd.com",
    "tmdb": "https://themoviedb.org",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# TMDB request rate-limiting (free tier allows ~40 req/10s)
REQUEST_DELAY = 0.3  # seconds between TMDB calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sanitize_filename(name: str) -> str:
    """Remove characters that are problematic in filenames."""
    # Replace colons, slashes, etc. with hyphens; strip leading/trailing spaces
    cleaned = re.sub(r'[\\/:*?"<>|]', "-", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Collapse multiple hyphens
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned


def fetch_tmdb_by_id(tmdb_id: int) -> dict | None:
    """Fetch movie details from TMDB by movie ID."""
    if not TMDB_API_KEY:
        return None
    url = f"{TMDB_BASE}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "append_to_response": "credits"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  [TMDB] Failed to fetch ID {tmdb_id}: {e}")
        return None


def search_tmdb(title: str, year: int) -> dict | None:
    """Search TMDB for a movie by title + year, then fetch full details."""
    if not TMDB_API_KEY:
        return None
    url = f"{TMDB_BASE}/search/movie"
    params = {"api_key": TMDB_API_KEY, "query": title, "year": year}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            # Retry without year constraint
            params.pop("year", None)
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        if results:
            return fetch_tmdb_by_id(results[0]["id"])
    except requests.RequestException as e:
        print(f"  [TMDB] Search failed for '{title}' ({year}): {e}")
    return None


def extract_tmdb_metadata(data: dict) -> dict:
    """Pull the fields we care about from a TMDB movie response."""
    # Director
    director = ""
    credits = data.get("credits", {})
    for crew in credits.get("crew", []):
        if crew.get("job") == "Director":
            director = crew["name"]
            break

    # Genres
    genres = [g["name"] for g in data.get("genres", [])]

    # Runtime
    runtime = data.get("runtime") or 0

    # Poster path
    poster_path = data.get("poster_path", "")

    return {
        "director": director,
        "genre": genres,
        "runtime": runtime,
        "poster_path": poster_path,
        "tmdb_id": data.get("id"),
    }


def download_poster(poster_path: str, filename: str) -> str | None:
    """Download a poster image and return the relative path for Obsidian."""
    if not poster_path:
        return None
    POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    img_url = f"{TMDB_IMG_BASE}{poster_path}"
    local_path = POSTERS_DIR / f"{filename}.jpg"
    if local_path.exists():
        return f"{POSTER_FOLDER}/{filename}.jpg"
    try:
        resp = requests.get(img_url, timeout=30)
        resp.raise_for_status()
        local_path.write_bytes(resp.content)
        return f"{POSTER_FOLDER}/{filename}.jpg"
    except requests.RequestException as e:
        print(f"  [POSTER] Failed to download: {e}")
        return None


def build_note(
    title: str,
    year: int,
    rating: float | None,
    watched_date: str,
    director: str,
    genre: list[str],
    runtime: int,
    poster_path: str | None,
    poster_rel: str | None,
    letterboxd_url: str = "",
) -> str:
    """Build an Obsidian markdown note with YAML frontmatter."""
    lines = ["---"]
    lines.append(f"title: \"{title}\"")
    lines.append(f"year: {year}")
    lines.append(f"director: \"{director}\"")

    # Genre as a YAML list
    if genre:
        genre_str = ", ".join(f"\"{g}\"" for g in genre)
        lines.append(f"genre: [{genre_str}]")
    else:
        lines.append("genre: []")

    lines.append(f"runtime: {runtime}")

    if rating is not None:
        lines.append(f"rating: {rating}")
    else:
        lines.append("rating: ")

    if watched_date:
        lines.append(f"watched_date: {watched_date}")

    # Image as a direct URL (used by Bases cards view via note.image)
    if poster_path:
        lines.append(f"image: {TMDB_IMG_BASE}{poster_path}")

    if letterboxd_url:
        lines.append(f"letterboxd: \"{letterboxd_url}\"")

    lines.append("---")
    lines.append("")

    # Body with embedded local poster for the note view
    if poster_rel:
        lines.append(f"![[{poster_rel}]]")
        lines.append("")

    return "\n".join(lines)


def write_note(filename: str, content: str) -> bool:
    """Write a note file. Returns True if a new note was created."""
    MOVIES_DIR.mkdir(parents=True, exist_ok=True)
    filepath = MOVIES_DIR / f"{filename}.md"
    if filepath.exists():
        return False
    filepath.write_text(content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# RSS sync
# ---------------------------------------------------------------------------


def parse_rss() -> list[dict]:
    """Fetch and parse the Letterboxd RSS feed."""
    print(f"Fetching RSS feed: {RSS_URL}")
    headers = {"User-Agent": "Mozilla/5.0 (letterboxd-obsidian-sync)"}
    resp = requests.get(RSS_URL, headers=headers, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    items = []

    for item in root.findall(".//item"):
        film_title = item.findtext("letterboxd:filmTitle", "", NS)
        film_year = item.findtext("letterboxd:filmYear", "0", NS)
        member_rating = item.findtext("letterboxd:memberRating", "", NS)
        watched_date = item.findtext("letterboxd:watchedDate", "", NS)
        tmdb_id = item.findtext("tmdb:movieId", "", NS)
        link = item.findtext("link", "")

        items.append(
            {
                "title": film_title,
                "year": int(film_year) if film_year else 0,
                "rating": float(member_rating) if member_rating else None,
                "watched_date": watched_date,
                "tmdb_id": int(tmdb_id) if tmdb_id else None,
                "letterboxd_url": link,
            }
        )

    print(f"Found {len(items)} entries in RSS feed.")
    return items


def sync_rss():
    """Sync movies from the RSS feed."""
    entries = parse_rss()
    created = 0
    skipped = 0

    for i, entry in enumerate(entries):
        title = entry["title"]
        year = entry["year"]
        safe_name = sanitize_filename(f"{title} ({year})")
        note_path = MOVIES_DIR / f"{safe_name}.md"

        if note_path.exists():
            skipped += 1
            continue

        print(f"  [{i+1}/{len(entries)}] {title} ({year})")

        # Fetch TMDB metadata
        meta = {"director": "", "genre": [], "runtime": 0, "poster_path": ""}
        if entry["tmdb_id"]:
            tmdb_data = fetch_tmdb_by_id(entry["tmdb_id"])
            if tmdb_data:
                meta = extract_tmdb_metadata(tmdb_data)
            time.sleep(REQUEST_DELAY)

        # Download poster
        poster_rel = download_poster(meta["poster_path"], safe_name)

        # Build and write note
        content = build_note(
            title=title,
            year=year,
            rating=entry["rating"],
            watched_date=entry["watched_date"],
            director=meta["director"],
            genre=meta["genre"],
            runtime=meta["runtime"],
            poster_path=meta["poster_path"],
            poster_rel=poster_rel,
            letterboxd_url=entry["letterboxd_url"],
        )

        if write_note(safe_name, content):
            created += 1
            print(f"    -> Created note")
        else:
            skipped += 1

    print(f"\nDone. Created: {created}, Skipped (already exist): {skipped}")


# ---------------------------------------------------------------------------
# Bulk CSV import
# ---------------------------------------------------------------------------


def parse_diary_csv(csv_path: str) -> list[dict]:
    """Parse a Letterboxd diary.csv export file."""
    entries = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("Name", "").strip()
            year = row.get("Year", "0").strip()
            rating = row.get("Rating", "").strip()
            watched_date = row.get("Watched Date", "").strip()
            letterboxd_uri = row.get("Letterboxd URI", "").strip()

            if not title:
                continue

            entries.append(
                {
                    "title": title,
                    "year": int(year) if year else 0,
                    "rating": float(rating) if rating else None,
                    "watched_date": watched_date,
                    "tmdb_id": None,  # CSV doesn't include TMDB IDs
                    "letterboxd_url": letterboxd_uri,
                }
            )

    print(f"Found {len(entries)} entries in diary CSV.")
    return entries


def sync_bulk(csv_path: str):
    """Bulk import from Letterboxd CSV export."""
    if not os.path.isfile(csv_path):
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    entries = parse_diary_csv(csv_path)
    created = 0
    skipped = 0
    failed = 0

    for i, entry in enumerate(entries):
        title = entry["title"]
        year = entry["year"]
        safe_name = sanitize_filename(f"{title} ({year})")
        note_path = MOVIES_DIR / f"{safe_name}.md"

        if note_path.exists():
            skipped += 1
            continue

        print(f"  [{i+1}/{len(entries)}] {title} ({year})")

        # Search TMDB by title + year (CSV has no TMDB IDs)
        meta = {"director": "", "genre": [], "runtime": 0, "poster_path": ""}
        tmdb_data = search_tmdb(title, year)
        if tmdb_data:
            meta = extract_tmdb_metadata(tmdb_data)
        else:
            print(f"    [!] Could not find on TMDB, creating note with limited data")
            failed += 1
        time.sleep(REQUEST_DELAY)

        # Download poster
        poster_rel = download_poster(meta["poster_path"], safe_name)

        # Build and write note
        content = build_note(
            title=title,
            year=year,
            rating=entry["rating"],
            watched_date=entry["watched_date"],
            director=meta["director"],
            genre=meta["genre"],
            runtime=meta["runtime"],
            poster_path=meta["poster_path"],
            poster_rel=poster_rel,
            letterboxd_url=entry["letterboxd_url"],
        )

        if write_note(safe_name, content):
            created += 1
            print(f"    -> Created note")
        else:
            skipped += 1

    print(f"\nDone. Created: {created}, Skipped: {skipped}, TMDB miss: {failed}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Sync Letterboxd movies to Obsidian notes."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--bulk",
        metavar="CSV_PATH",
        help="Path to Letterboxd diary.csv export file for bulk import.",
    )
    group.add_argument(
        "--rss",
        action="store_true",
        help="Sync latest entries from the Letterboxd RSS feed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files.",
    )

    args = parser.parse_args()

    # Validate TMDB key
    if not TMDB_API_KEY:
        print("WARNING: No TMDB_API_KEY set in .env file.")
        print("Notes will be created without director, genre, runtime, or poster.")
        print("Get a free key at: https://www.themoviedb.org/settings/api\n")

    # Ensure output directories exist
    MOVIES_DIR.mkdir(parents=True, exist_ok=True)

    if args.bulk:
        sync_bulk(args.bulk)
    elif args.rss:
        sync_rss()


if __name__ == "__main__":
    main()
