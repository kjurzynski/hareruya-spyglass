from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx


SCRYFALL_CARDMARKET_URL = "https://api.scryfall.com/cards/cardmarket/{product_id}"
SCRYFALL_USER_AGENT = "HareruyaSpyglass/1.1"
SCRYFALL_ACCEPT = "application/json;q=0.9,*/*;q=0.8"
SCRYFALL_TIMEOUT = 10.0
SCRYFALL_MIN_REQUEST_INTERVAL = 0.12


class ScryfallError(RuntimeError):
    """Raised when a Scryfall lookup cannot be completed."""


@dataclass(frozen=True)
class ScryfallCardInfo:
    image_url: str | None
    promo_types: tuple[str, ...] = ()
    promo_type_labels: tuple[str, ...] = ()


_CACHE_EMPTY = ScryfallCardInfo(image_url=None)
_cache: dict[int, ScryfallCardInfo | None] = {}
_cache_lock = threading.Lock()
_request_lock = threading.Lock()
_last_request_at = 0.0


# Scryfall's current promo_type vocabulary contains a small family of foil
# variants. These labels make those values readable while leaving non-foil
# promo categories such as universesbeyond out of the UI.
_PROMO_TYPE_LABELS = {
    "confettifoil": "Confetti Foil",
    "fracturefoil": "Fracture Foil",
    "galaxyfoil": "Galaxy Foil",
    "halofoil": "Halo Foil",
    "manafoil": "Mana Foil",
    "rainbowfoil": "Rainbow Foil",
    "raisedfoil": "Raised Foil",
    "ripplefoil": "Ripple Foil",
    "silverfoil": "Silver Foil",
    "surgefoil": "Surge Foil",
    "texturedfoil": "Textured Foil",
    "shatteredglassfoil": "Shattered Glass Foil",
    "doublerainbow": "Double Rainbow Foil",
    "foiletched": "Foil Etched",
    "etchedfoil": "Etched Foil",
    "serialized": "Serialized",
}


def _cached(product_id: int) -> tuple[bool, ScryfallCardInfo | None]:
    with _cache_lock:
        if product_id in _cache:
            return True, _cache[product_id]
    return False, None


def _store(product_id: int, info: ScryfallCardInfo | None) -> None:
    with _cache_lock:
        _cache[product_id] = info


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


def _normalise_promo_type(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _fallback_promo_label(key: str) -> str | None:
    if key == "serialized":
        return "Serialized"
    if "foil" not in key:
        return None
    if key.startswith("foil") and len(key) > 4:
        stem = key[4:]
        return f"Foil {stem.title()}"
    if key.endswith("foil") and len(key) > 4:
        stem = key[:-4]
        return f"{stem.title()} Foil"
    return key.title()


def _promo_type_labels(promo_types: list[Any]) -> tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()
    serialized_seen = False
    for raw in promo_types:
        key = _normalise_promo_type(raw)
        if not key or key in seen:
            continue
        if key == "serialized":
            serialized_seen = True
            seen.add(key)
            continue
        label = _PROMO_TYPE_LABELS.get(key) or _fallback_promo_label(key)
        if label:
            labels.append(label)
            seen.add(key)
    if serialized_seen:
        labels.append("Serialized")
    return tuple(labels)


def _card_info(payload: dict[str, Any]) -> ScryfallCardInfo:
    raw_promo_types = payload.get("promo_types")
    promo_types = tuple(
        str(value).strip()
        for value in raw_promo_types
        if isinstance(raw_promo_types, list) and isinstance(value, str) and value.strip()
    ) if isinstance(raw_promo_types, list) else ()
    return ScryfallCardInfo(
        image_url=_normal_image_url(payload),
        promo_types=promo_types,
        promo_type_labels=_promo_type_labels(list(promo_types)),
    )


def get_cardmarket_card_info(product_id: int) -> ScryfallCardInfo | None:
    """Resolve a Cardmarket product ID to Scryfall image and promo metadata."""
    if not isinstance(product_id, int) or product_id <= 0:
        raise ValueError("Cardmarket product ID must be a positive integer.")

    found, cached = _cached(product_id)
    if found:
        return cached

    # Serialize misses so the application stays comfortably below Scryfall's
    # published API request-rate guidance even when several images load at once.
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
            raise ScryfallError("Scryfall lookup failed.") from exc

        if not isinstance(payload, dict):
            raise ScryfallError("Scryfall returned an unexpected response.")

        info = _card_info(payload)
        _store(product_id, info)
        return info


def get_cardmarket_image_url(product_id: int) -> str | None:
    """Resolve a Cardmarket product ID to Scryfall's normal image URL."""
    info = get_cardmarket_card_info(product_id)
    return info.image_url if info else None
