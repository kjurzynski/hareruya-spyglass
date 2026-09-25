from __future__ import annotations

from decimal import Decimal

import httpx

EUR_JPY_URL = "https://api.frankfurter.dev/v2/rate/eur/jpy"


def yen_to_eur(yen: int | Decimal, eur_jpy_rate: Decimal) -> Decimal:
    if eur_jpy_rate <= 0:
        raise ValueError("EUR/JPY rate must be positive.")
    return Decimal(str(yen)) / eur_jpy_rate


def get_eur_jpy_rate(timeout: float = 10.0) -> Decimal:
    """Return the latest EUR→JPY rate from Frankfurter."""
    with httpx.Client(timeout=timeout) as client:
        response = client.get(EUR_JPY_URL)
        response.raise_for_status()
        data = response.json()

    try:
        rate = Decimal(str(data["rate"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Currency service returned an invalid EUR/JPY rate.") from exc

    if rate <= 0:
        raise RuntimeError("Currency service returned a non-positive EUR/JPY rate.")
    return rate
