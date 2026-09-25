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
- Price cells also show a EUR conversion using the latest EUR/JPY rate fetched once per search.

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

On a phone, the mobile UI is selected automatically. Use the `Switch to Desktop view` / `Switch to Mobile view` button in the header to force either layout while testing on a desktop.

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

The scraper also uses bounded concurrency. The EUR/JPY rate is fetched from Frankfurter at job start and is not hard-coded. If that service is temporarily unavailable, yen prices still render. For a public deployment, add persistent job storage, caching, rate limiting, and a dedicated worker queue before accepting substantial traffic.
