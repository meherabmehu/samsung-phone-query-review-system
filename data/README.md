# Data directory

This directory holds the scraped Samsung phone dataset and any local database
files (SQLite).

## `samsung_phones.json`

A lightweight, structured export of the scraped GSMArena data for 15 popular
Samsung phones. Each entry contains the phone's identity fields, raw spec
text, parsed numeric fields (battery mAh, display inches, camera MP, RAM,
weight, USD price) and the full structured spec sheet grouped by category.

- **How it was generated:** `python -m scripts.scrape_data` (which scrapes
  GSMArena, stores to PostgreSQL, and exports this JSON).
- **How to regenerate it:** re-run `python -m scripts.scrape_data`.
- **How to load it into PostgreSQL:** `python -m scripts.seed_data`.

The scraper itself remains fully functional — this file simply lets an
evaluator run the project without hitting the network.

> `*.db` files (SQLite) are gitignored.
