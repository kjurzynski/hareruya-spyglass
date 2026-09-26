from __future__ import annotations

from decimal import Decimal, InvalidOperation

import httpx

EUR_JPY_URL = "https://api.frankfurter.dev/v2/rate/eur/jpy"


def get_eur_jpy_rate(timeout: float = 10.0) -> Decimal:
    response = httpx.get(EUR_JPY_URL, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    try:
        rate = Decimal(str(data["rate"]))
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise RuntimeError("Frankfurter returned an invalid EUR/JPY rate.") from exc
    if rate <= 0:
        raise RuntimeError("Frankfurter returned a non-positive EUR/JPY rate.")
    return rate


def yen_to_eur(yen: int, eur_jpy_rate: Decimal) -> Decimal:
    return (Decimal(yen) / eur_jpy_rate).quantize(Decimal("0.01"))
