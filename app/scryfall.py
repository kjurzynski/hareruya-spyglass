from __future__ import annotations

import threading
import time
from typing import Any

import httpx


SCRYFALL_CARDMARKET_URL = "https://api.scryfall.com/cards/cardmarket/{product_id}"
SCRYFALL_USER_AGENT = "HareruyaSpyglass/1.1"
SCRYFALL_ACCEPT = "application/json;q=0.9,*/*;q=0.8"
SCRYFALL_TIMEOUT = 10.0
SCRYFALL_MIN_REQUEST_INTERVAL = 0.12


class ScryfallError(RuntimeError):
    """Raised when a Scryfall image lookup cannot be completed."""


_cache: dict[int, str | None] = {}
_cache_lock = threading.Lock()
_request_lock = threading.Lock()
_last_request_at = 0.0


def _cached(product_id: int) -> tuple[bool, str | None]:
    with _cache_lock:
        if product_id in _cache:
            return True, _cache[product_id]
    return False, None


def _store(product_id: int, image_url: str | None) -> None:
    with _cache_lock:
        _cache[product_id] = image_url


def _throttle() -> None:
    global _last_request_at
    now = time.monotonic()
    wait = SCRYFALL_MIN_REQUEST_INTERVAL - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _normal_image_url(payload: dict[str, Any]) -> str | None:
    image_uris = payload.get("image_uris")
    if not isinstance(image_uris, dict):
        return None
    normal = image_uris.get("normal")
    if not isinstance(normal, str):
        return None
    normal = normal.strip()
    return normal or None


def get_cardmarket_image_url(product_id: int) -> str | None:
    """Resolve a Cardmarket product ID to Scryfall's normal image URL."""
    if not isinstance(product_id, int) or product_id <= 0:
        raise ValueError("Cardmarket product ID must be a positive integer.")

    found, cached = _cached(product_id)
    if found:
        return cached

    # Serialize misses so the application stays comfortably below Scryfall's
    # published API request-rate guidance even when several mobile images load
    # at once. Cached lookups do not enter this lock.
    with _request_lock:
        found, cached = _cached(product_id)
        if found:
            return cached

        _throttle()
        url = SCRYFALL_CARDMARKET_URL.format(product_id=product_id)
        headers = {
            "User-Agent": SCRYFALL_USER_AGENT,
            "Accept": SCRYFALL_ACCEPT,
        }
        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=SCRYFALL_TIMEOUT) as client:
                response = client.get(url)
            if response.status_code == 404:
                _store(product_id, None)
                return None
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ScryfallError(f"Scryfall returned HTTP {exc.response.status_code}.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ScryfallError("Scryfall image lookup failed.") from exc

        if not isinstance(payload, dict):
            raise ScryfallError("Scryfall returned an unexpected response.")

        image_url = _normal_image_url(payload)
        _store(product_id, image_url)
        return image_url
