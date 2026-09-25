from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .jobs import JobManager
from .models import CardResultOut, CheckRequest, JobCreated, JobStatus, ListingOut

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="Hareruya Spyglass", version="1.0.0")
manager = JobManager(max_jobs=2)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


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
    if len(cards) > 110:
        raise HTTPException(status_code=400, detail="Maximum 110 cards per job.")
    job = manager.create(cards, request.finish, request.output)
    return JobCreated(job_id=job.job_id)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    results = [
        CardResultOut(
            card_name=result.card_name,
            rows=[
                ListingOut(
                    price=row.price,
                    language=row.language,
                    expansion=row.expansion,
                    foil=row.foil,
                    title=row.title,
                    stock=row.stock,
                    url=row.url,
                    image_url=row.image_url,
                )
                for row in result.rows
            ],
            error=result.error,
        )
        for result in job.results
    ]

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
