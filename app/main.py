from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cardmarket_jobs import CardmarketUpdateManager, start_daily_scheduler, status_payload
from .cardmarket_data import LOCAL_INDEX
from .jobs import JobManager
from .models import (
    CardResultOut,
    CardmarketPriceOut,
    CardmarketVariantOut,
    CheckRequest,
    JobCreated,
    JobStatus,
    ListingOut,
)

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="Hareruya MTG Price Checker", version="1.0.0")
manager = JobManager(max_jobs=2)
cardmarket_manager = CardmarketUpdateManager()
start_daily_scheduler(cardmarket_manager)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/cardmarket", include_in_schema=False)
def cardmarket_page():
    return FileResponse(BASE_DIR / "static" / "cardmarket.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/jobs", response_model=JobCreated)
def create_job(request: CheckRequest):
    cards = []
    seen = set()
    for card in request.cards:
        card = " ".join(card.split()).strip()
        if card and card.casefold() not in seen:
            cards.append(card)
            seen.add(card.casefold())
    if not cards:
        raise HTTPException(status_code=400, detail="No card names were supplied.")
    if len(cards) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 cards per job.")
    job = manager.create(cards, request.finish, request.output, request.language)
    return JobCreated(job_id=job.job_id)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    results = []
    for result in job.results:
        listing_out = []
        for row in result.rows:
            cardmarket_row = LOCAL_INDEX.lookup(result.card_name, row.expansion, row.foil, row.title)
            cardmarket = None
            if cardmarket_row:
                nonfoil = cardmarket_row.get("nonfoil") or {}
                foil = cardmarket_row.get("foil")
                cardmarket = CardmarketPriceOut(
                    product_id=int(cardmarket_row["product_id"]),
                    card_name=str(cardmarket_row.get("card_name", result.card_name)),
                    expansion=str(cardmarket_row.get("expansion", row.expansion)),
                    expansion_name=str(cardmarket_row.get("expansion_name", "")),
                    nonfoil=CardmarketVariantOut(**nonfoil),
                    foil=CardmarketVariantOut(**foil) if isinstance(foil, dict) else None,
                    cardmarket_url=str(cardmarket_row.get("cardmarket_url", "")),
                    ambiguous=bool(cardmarket_row.get("ambiguous", False)),
                    ambiguity_reason=str(cardmarket_row.get("ambiguity_reason", "")),
                )
            listing_out.append(
                ListingOut(
                    price=row.price,
                    language=row.language,
                    expansion=row.expansion,
                    foil=row.foil,
                    title=row.title,
                    stock=row.stock,
                    url=row.url,
                    image_url=row.image_url,
                    cardmarket=cardmarket,
                )
            )
        results.append(
            CardResultOut(
                card_name=result.card_name,
                rows=listing_out,
                error=result.error,
            )
        )

    return JobStatus(
        job_id=job.job_id,
        status=job.status,
        completed=job.completed,
        total=len(job.cards),
        results=results,
        error=job.error,
        output=job.output,
        eur_jpy_rate=job.eur_jpy_rate,
    )


@app.get("/api/cardmarket/status")
def get_cardmarket_status():
    return status_payload(cardmarket_manager)


@app.get("/api/cardmarket/table")
def get_cardmarket_table(
    q: str = "",
    expansion: str = "",
    exact: bool = False,
    page: int = 1,
    page_size: int = 100,
):
    from .cardmarket_data import load_merged_rows, normalize_name

    page = max(1, page)
    page_size = max(1, min(200, page_size))
    wanted = normalize_name(q)
    wanted_expansion = normalize_name(expansion)
    rows = []
    for row in load_merged_rows():
        card_name = normalize_name(str(row.get("card_name", "")))
        if wanted and (card_name != wanted if exact else wanted not in card_name):
            continue
        if wanted_expansion and wanted_expansion != normalize_name(str(row.get("expansion", ""))):
            continue
        rows.append(row)
    start = (page - 1) * page_size
    return {"page": page, "page_size": page_size, "total": len(rows), "rows": rows[start:start + page_size]}
