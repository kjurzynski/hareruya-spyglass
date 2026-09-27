# Hareruya Spyglass Web App

A local web version of the supplied Hareruya price-checking Python program.

## Features

Version 1.0.0

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

The project has a separate, disk-backed Cardmarket importer. It downloads Cardmarket's public Magic singles product list and price guide, creates a durable expansion-ID reference map, and writes the merged table under `data/cardmarket/`. The Hareruya search never contacts Cardmarket for this enrichment; it only reads the local merged snapshot. The raw downloads, merged files, status file, and unmapped-ID report are generated automatically during the first refresh and subsequent daily updates.

- `data/cardmarket/raw/price_guide_1.json` — generated raw Cardmarket price guide.
- `data/cardmarket/raw/products_singles_1.json` — generated raw Cardmarket singles catalog.
- `data/cardmarket/merged/cardmarket_prices.json` — generated data used by the web app for lookups.
- `data/cardmarket/merged/cardmarket_prices.csv` — generated human-readable copy of the merged table.
- `data/cardmarket/reference/expansion_ids_map.txt` — bundled Cardmarket expansion-ID -> short set-code/name map used directly by the merger. The file contains 766 Cardmarket expansion IDs, with short codes for 761 of them.
- `data/cardmarket/reference/unmapped_expansion_ids.json` — expansion IDs present in the current Cardmarket catalog that are not covered by the map.
- `data/cardmarket/reference/expansion_overrides.json` — optional manual corrections for exceptional IDs.
- `data/cardmarket/status.json` — timestamp, source counts, map coverage, and current local dataset status.

The expansion map is bundled with the application rather than downloaded from an external set-list service. The merger reads `expansion_ids_map.txt` directly on every refresh, so the Cardmarket `idExpansion` -> expansion name/code mapping is available offline once the application is installed. The bundled map was checked against the current Cardmarket singles catalog: all 766 distinct `idExpansion` values present in the supplied catalog are represented in the bundled map. Short-code normalization is applied consistently: 4-character codes beginning with `X` or `P` drop that first character, and any code containing `SLD` is represented as `SLD`; all other codes remain unchanged.

The updater still checks every `idExpansion` present in the current Cardmarket singles catalog and records anything not covered by the bundled map (or a retained local override map) in `unmapped_expansion_ids.json`. This means newly introduced Cardmarket expansion IDs will be reported rather than guessed.
When multiple Cardmarket records match the same Hareruya card name and expansion, the Hareruya Cardmarket section selects the record with the cheapest relevant trend price. For Hareruya titles containing `【Surge・Foil】`, `■RetroF■`, `【Galaxy Foil】`, `【Chocobo Track・Foil】`, `【Foil Etched】`, or `【Fracture・Foil】`, it instead selects the most expensive relevant trend price. The relevant trend is non-foil for non-foil Hareruya results and foil trend for foil results.


The two Cardmarket raw files are the only files downloaded during a normal daily refresh. No MTGJSON expansion-map request is made.

On environment startup, the app checks whether the local snapshot is current and refreshes it when needed. A background scheduler then runs the refresh automatically every day at 04:00 Europe/Warsaw. There is no user-facing update control. After an update completes, Hareruya result enrichment reads only `data/cardmarket/merged/cardmarket_prices.json`.

The local merged table can be browsed at `http://127.0.0.1:8000/cardmarket`. The main page exposes only a small link to this read-only view. Searches and pagination on that page read the generated local JSON and do not contact Cardmarket or MTGJSON.

