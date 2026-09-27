from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

Finish = Literal["foil", "nonfoil", "all"]
Language = Literal["all", "EN", "JP"]
OutputMode = Literal["individual", "cheapest", "both"]


class CheckRequest(BaseModel):
    cards: list[str] = Field(min_length=1, max_length=100)
    finish: Finish = "all"
    language: Language = "all"
    output: OutputMode = "cheapest"


class CardmarketVariantOut(BaseModel):
    low: float | None = None
    trend: float | None = None
    avg7: float | None = None
    avg30: float | None = None


class CardmarketPriceOut(BaseModel):
    product_id: int
    card_name: str
    expansion: str
    expansion_name: str = ""
    nonfoil: CardmarketVariantOut
    foil: CardmarketVariantOut | None = None
    cardmarket_url: str
    ambiguous: bool = False
    ambiguity_reason: str = ""


class ListingOut(BaseModel):
    price: int
    language: str
    expansion: str
    foil: bool
    title: str
    stock: int
    url: str
    image_url: str
    cardmarket: CardmarketPriceOut | None = None


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
    results: list[CardResultOut] = Field(default_factory=list)
    error: str | None = None
    output: OutputMode = "cheapest"
    eur_jpy_rate: float | None = None
