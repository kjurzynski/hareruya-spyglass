# Hareruya Spyglass Web App

A local web version of the supplied Hareruya price-checking Python program.

## Features

- Paste a card list directly into the browser.
- Choose `all`, `foil`, or `nonfoil` listings.
- Choose one output mode: `Cheapest (one option per card)`, `Individual (all listings for each card)`, or `Both`.
- Show `All results` for each card in switchable tabs instead of a long list of tables.
- Sort tables by price, language, expansion, finish, or full title by clicking column headers.
- Filter each table by maximum price, language, expansion, finish, and title text.
- Open the individual Hareruya product/listing link in a new browser tab.
- Preview card images in a floating overlay that stays fully inside the browser viewport.
- Size result windows to the table content while keeping them centered; horizontal scrolling appears only when content exceeds the viewport.
- Background jobs with progress polling, elapsed-time display, and ETA for searches of 10 or more cards.

## Local setup

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

### macOS/Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

API documentation is available at http://127.0.0.1:8000/docs

## Testing

Run the automated Python tests with:

```bash
pytest
```

The tests cover the API models and core HTML parser behavior. The live Hareruya scrape is not part of the automated test suite because it depends on the current external website.

## Configuration

Copy `.env.example` to `.env` if you want to change the maximum number of Hareruya result pages crawled for one card.

`HARERUYA_MAX_PAGES=20`

The scraper also uses bounded concurrency. For a public deployment, add persistent job storage, caching, rate limiting, and a dedicated worker queue before accepting substantial traffic.

## Cardmarket daily price data

The project has a separate, disk-backed Cardmarket importer. It downloads Cardmarket's public Magic singles product list and price guide, creates a durable expansion-ID reference map, and writes the merged table under `data/cardmarket/`. The Hareruya search never contacts Cardmarket for this enrichment; it only reads the local merged snapshot.

- `data/cardmarket/raw/price_guide_1.json` — latest raw Cardmarket price guide.
- `data/cardmarket/raw/products_singles_1.json` — latest raw Cardmarket singles catalog.
- `data/cardmarket/merged/cardmarket_prices.json` — merged data used by the web app for lookups.
- `data/cardmarket/merged/cardmarket_prices.csv` — human-readable copy of the merged table.
- `data/cardmarket/reference/cardmarket_expansion_set_map.json` — persistent Cardmarket `idExpansion` -> MTGJSON short set-code map.
- `data/cardmarket/reference/expansion_map.csv` — bundled external Cardmarket expansion-ID map used as a fallback to fill IDs that MTGJSON does not resolve.
- `data/cardmarket/reference/cardmarket_expansion_set_map_status.json` — when that map was built and how many expansion IDs it contains.
- `data/cardmarket/reference/unmapped_expansion_ids.json` — expansion IDs present in the current Cardmarket catalog that are not covered by the map.
- `data/cardmarket/reference/expansion_overrides.json` — optional manual corrections for exceptional IDs.
- `data/cardmarket/status.json` — timestamp, source counts, map coverage, and current local dataset status.

The expansion map is built as its own persisted step before the merged price table is written. The source is MTGJSON's `SetList`, whose set metadata includes `mcmId` and `mcmIdExtras` (Cardmarket set identifiers) alongside the set `code` and name. Both Cardmarket expansion identifiers are mapped to the corresponding short set code. MTGJSON documents `mcmId` as the Cardmarket set identifier and `mcmIdExtras` as the split Cardmarket set identifier for sets printed in two sets. citeturn719177search1turn929334search4 citeturn929334search4turn929334search11

On each daily refresh, the updater first downloads the two Cardmarket raw files. It then refreshes the small MTGJSON SetList source, builds `cardmarket_expansion_set_map.json`, and records its coverage before performing the price/catalog merge. The raw MTGJSON SetList file is temporary and is removed after the map has been written.

The updater also compares every `idExpansion` present in the current Cardmarket singles catalog against the persisted map and records unresolved IDs in `unmapped_expansion_ids.json`. This means missing expansion mappings are measured against the actual downloaded catalog, not just against products that happen to have prices. If the latest MTGJSON refresh fails but a previous local map exists, the previous map is used so the price refresh can still complete; new/unmapped expansions are reported instead of making the whole dataset unusable.

On environment startup, the app checks whether the local snapshot is current and refreshes it when needed. A background scheduler then runs the refresh automatically every day at 04:00 Europe/Warsaw. There is no user-facing update control. After an update completes, Hareruya result enrichment reads only `data/cardmarket/merged/cardmarket_prices.json`.

The local merged table can be browsed at `http://127.0.0.1:8000/cardmarket`. The main page exposes only a small link to this read-only view. Searches and pagination on that page read the generated local JSON and do not contact Cardmarket or MTGJSON.

The reference directory also contains `card_catalog_verified_expansion_map.json`. This is a small, evidence-backed fallback built from Cardmarket catalog products whose expansion IDs were separately verified against their exact Cardmarket set codes. It is used only after the existing MTGJSON and bundled external maps, and unmapped IDs remain reported rather than being guessed.
