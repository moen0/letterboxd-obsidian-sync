# Letterboxd to Obsidian Sync

Automatically import your Letterboxd movie diary into Obsidian as markdown notes with full metadata and poster images.

Each movie becomes a note with YAML properties (title, year, director, genre, runtime, rating, poster) pulled from the TMDB API, ready to use with Obsidian Bases or Dataview.

## Setup

1. Get a free TMDB API key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)

2. Install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Configure:
```bash
cp .env.example .env
# Edit .env and add your TMDB API key
```

## Usage

### Bulk import (full history)

Export your data from [letterboxd.com/settings/data/](https://letterboxd.com/settings/data/), unzip, and run:

```bash
python sync.py --bulk /path/to/diary.csv
```

### RSS sync (latest 50 entries)

```bash
python sync.py --rss
```

### Automatic sync

Run `./setup.sh` to install a macOS launchd job that syncs every 6 hours.

## Configuration

All settings are in the `.env` file:

| Variable | Description |
|---|---|
| `TMDB_API_KEY` | Your TMDB API key |
| `LETTERBOXD_USERNAME` | Your Letterboxd username |
| `OBSIDIAN_VAULT_PATH` | Path to your Obsidian vault |
| `MOVIE_FOLDER` | Folder inside the vault for movie notes |

## Generated note format

```yaml
---
title: "There Will Be Blood"
year: 2007
director: "Paul Thomas Anderson"
genre: ["Drama"]
runtime: 158
rating: 5.0
watched_date: 2026-03-17
image: https://image.tmdb.org/t/p/w500/...
letterboxd: "https://letterboxd.com/..."
---
```
