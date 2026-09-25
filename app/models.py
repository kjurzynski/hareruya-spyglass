from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

Finish = Literal["foil", "nonfoil", "all"]
OutputMode = Literal["individual", "cheapest", "both"]


class CheckRequest(BaseModel):
    cards: list[str] = Field(min_length=1, max_length=100)
    finish: Finish = "all"
    output: OutputMode = "cheapest"


class ListingOut(BaseModel):
    price: int
    language: str
    expansion: str
    foil: bool
    title: str
    stock: int
    url: str
    image_url: str


class CardResultOut(BaseModel):
    card_name: str
    rows: list[ListingOut]
    error: str | None = None
    output: OutputMode = "cheapest"


class JobCreated(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "complete", "error"]
    completed: int
    total: int
    results: list[CardResultOut] = []
    error: str | None = None
    output: OutputMode = "cheapest"
