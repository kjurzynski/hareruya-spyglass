from __future__ import annotations

import csv
import json
import os
import re
import gzip
import io
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlencode

import httpx


CARDMARKET_PRICE_GUIDE_URL = (
    "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_1.json"
)
CARDMARKET_PRODUCT_LIST_URL = (
    "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_1.json"
)
MTGJSON_SET_LIST_URL = "https://mtgjson.com/api/v5/SetList.json.gz"

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "cardmarket"
RAW_DIR = DATA_ROOT / "raw"
REFERENCE_DIR = DATA_ROOT / "reference"
MERGED_DIR = DATA_ROOT / "merged"
PRICE_GUIDE_FILE = RAW_DIR / "price_guide_1.json"
PRODUCT_LIST_FILE = RAW_DIR / "products_singles_1.json"
EXPANSION_SET_MAP_FILE = REFERENCE_DIR / "cardmarket_expansion_set_map.json"
EXPANSION_SET_MAP_STATUS_FILE = REFERENCE_DIR / "cardmarket_expansion_set_map_status.json"
MTGJSON_SET_LIST_FILE = RAW_DIR / "mtgjson_set_list.json.gz"
EXPANSION_OVERRIDES_FILE = REFERENCE_DIR / "expansion_overrides.json"
SUPPLEMENTAL_EXPANSION_MAP_FILE = REFERENCE_DIR / "expansion_map.csv"
CATALOG_VERIFIED_EXPANSION_MAP_FILE = REFERENCE_DIR / "card_catalog_verified_expansion_map.json"
MERGED_JSON_FILE = MERGED_DIR / "cardmarket_prices.json"
MERGED_CSV_FILE = MERGED_DIR / "cardmarket_prices.csv"
STATUS_FILE = DATA_ROOT / "status.json"

_LEGACY_AVG7_CACHE_MTIME_NS: int | None = None
_LEGACY_AVG7_CACHE: dict[int, tuple[float | None, float | None]] = {}
UNMAPPED_FILE = REFERENCE_DIR / "unmapped_expansion_ids.json"

USER_AGENT = "Hareruya-Spyglass-Cardmarket-Importer/1.0"


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    expansion_id: int | None
    metacard_id: int | None


@dataclass(frozen=True)
class PriceGuide:
    product_id: int
    low: Decimal | None
    trend: Decimal | None
    avg7: Decimal | None
    avg30: Decimal | None
    low_foil: Decimal | None
    trend_foil: Decimal | None
    avg7_foil: Decimal | None
    avg30_foil: Decimal | None


ProgressCallback = Callable[[float, str], None]


def _ensure_dirs() -> None:
    for directory in (RAW_DIR, REFERENCE_DIR, MERGED_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
    os.replace(temp_path, path)


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_bytes(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8"),
    )


def _clean_text(value: str) -> str:
    return " ".join(str(value).split())


def normalize_name(value: str) -> str:
    return _clean_text(unicodedata.normalize("NFKC", value)).casefold()


def _as_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _as_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "null"):
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if result <= 0:
        return None
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    folded = {str(key).casefold(): value for key, value in row.items()}
    for name in names:
        if name.casefold() in folded:
            return folded[name.casefold()]
    return None


def _iter_rows(payload: Any, preferred_keys: tuple[str, ...]) -> Iterator[dict[str, Any]]:
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                yield row
        return
    if not isinstance(payload, dict):
        return

    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    yield row
            return
        if isinstance(value, dict):
            for identifier, row in value.items():
                if isinstance(row, dict):
                    row = dict(row)
                    row.setdefault("idProduct", identifier)
                    yield row
            return

    # Some exports are a direct {"123": {...}} map.
    for identifier, row in payload.items():
        if isinstance(row, dict):
            row = dict(row)
            row.setdefault("idProduct", identifier)
            yield row


def parse_product_list(payload: Any) -> dict[int, Product]:
    products: dict[int, Product] = {}
    for row in _iter_rows(payload, ("products", "productList", "data", "results")):
        product_id = _as_int(_field(row, "idProduct", "productId", "Product ID"))
        if product_id is None:
            continue
        products[product_id] = Product(
            product_id=product_id,
            name=_clean_text(str(_field(row, "name", "productName") or "")),
            expansion_id=_as_int(_field(row, "idExpansion", "expansionId", "Expansion ID")),
            metacard_id=_as_int(_field(row, "idMetacard", "metacardId")),
        )
    return products


def parse_price_guide(payload: Any) -> dict[int, PriceGuide]:
    prices: dict[int, PriceGuide] = {}
    for row in _iter_rows(payload, ("priceGuides", "priceGuide", "prices", "data", "results")):
        product_id = _as_int(_field(row, "idProduct", "productId"))
        if product_id is None:
            continue
        prices[product_id] = PriceGuide(
            product_id=product_id,
            low=_as_decimal(_field(row, "low", "Low Price")),
            trend=_as_decimal(_field(row, "trend", "Trend Price")),
            avg7=_as_decimal(_field(row, "avg7", "avg-7", "AVG7", "AVG 7")),
            avg30=_as_decimal(_field(row, "avg30", "avg-30", "AVG30")),
            low_foil=_as_decimal(_field(row, "low-foil", "lowFoil", "foilLow", "Foil Low")),
            trend_foil=_as_decimal(_field(row, "trend-foil", "trendFoil", "foilTrend", "Foil Trend")),
            avg7_foil=_as_decimal(_field(row, "avg7-foil", "avg7Foil", "foilAvg7", "Foil AVG7", "Foil AVG 7")),
            avg30_foil=_as_decimal(_field(row, "avg30-foil", "avg30Foil", "foilAvg30", "Foil AVG30")),
        )
    return prices


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_download_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
            return handle.read()
    return raw


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _download_rows(path: Path) -> Any:
    """Read Cardmarket's current JSON or CSV download formats.

    Cardmarket's public download files use .json filenames, but the published
    price-guide format is a gzipped CSV. Detect the actual content instead of
    relying on the filename.
    """
    data = _read_download_bytes(path)
    text = data.decode("utf-8-sig", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(text)

    sample = "\n".join(text.splitlines()[:10])
    reader = csv.DictReader(io.StringIO(text), delimiter=_sniff_delimiter(sample))
    rows = []
    for row in reader:
        rows.append({str(key).strip(): (value or "").strip() for key, value in row.items()})
    return rows


def load_products() -> dict[int, Product]:
    return parse_product_list(_download_rows(PRODUCT_LIST_FILE)) if PRODUCT_LIST_FILE.exists() else {}


def load_prices() -> dict[int, PriceGuide]:
    return parse_price_guide(_download_rows(PRICE_GUIDE_FILE)) if PRICE_GUIDE_FILE.exists() else {}


def load_expansion_set_map() -> dict[str, dict[str, str]]:
    if not EXPANSION_SET_MAP_FILE.exists():
        return {}
    try:
        raw = _load_json(EXPANSION_SET_MAP_FILE)
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_expansion_overrides() -> dict[str, str]:
    if not EXPANSION_OVERRIDES_FILE.exists():
        return {}
    raw = _load_json(EXPANSION_OVERRIDES_FILE)
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def load_supplemental_expansion_map() -> dict[str, dict[str, str]]:
    """Load the bundled external Cardmarket-ID -> short-code/name fallback map."""
    if not SUPPLEMENTAL_EXPANSION_MAP_FILE.exists():
        return {}

    mapping: dict[str, dict[str, str]] = {}
    try:
        with SUPPLEMENTAL_EXPANSION_MAP_FILE.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                expansion_id = _as_int(_field(row, "id_expansion", "idExpansion"))
                if expansion_id is None:
                    continue
                code = _clean_text(str(_field(row, "expansion_code", "expansion_codes") or "")).strip().upper()
                name = _clean_text(str(_field(row, "expansion_name") or "")).strip()
                if not code and not name:
                    continue
                mapping[str(expansion_id)] = {"code": code, "name": name, "source": "external_csv"}
    except (OSError, csv.Error):
        return {}
    return mapping


def load_catalog_verified_expansion_map() -> dict[str, dict[str, str]]:
    """Load only manually verified expansion mappings derived from the Cardmarket product catalog.

    These mappings are deliberately kept separate from the broader external fallback map.
    Each entry has a concrete evidence card and verification note so we never infer a code
    merely from suggestive card names.
    """
    if not CATALOG_VERIFIED_EXPANSION_MAP_FILE.exists():
        return {}
    try:
        raw = _load_json(CATALOG_VERIFIED_EXPANSION_MAP_FILE)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    mapping: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        code = _clean_text(str(value.get("code") or "")).strip().upper()
        name = _clean_text(str(value.get("name") or "")).strip()
        if not code and not name:
            continue
        entry = {
            "code": code,
            "name": name,
            "source": "catalog_verified",
        }
        for field in ("evidence_card", "evidence_note"):
            if value.get(field):
                entry[field] = str(value[field])
        mapping[str(key)] = entry
    return mapping


def parse_mtgjson_set_list(payload: Any) -> dict[str, dict[str, str]]:
    """Build Cardmarket expansion-ID -> MTGJSON short set-code mapping."""
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(rows, dict):
        rows = rows.values()
    if not isinstance(rows, (list, tuple)) and not hasattr(rows, "__iter__"):
        return {}

    mapping: dict[str, dict[str, str]] = {}
    conflicts: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip().upper()
        name = _clean_text(str(row.get("name") or row.get("mcmName") or ""))
        if not code:
            continue
        for field in ("mcmId", "mcmIdExtras"):
            expansion_id = _as_int(row.get(field))
            if expansion_id is None:
                continue
            key = str(expansion_id)
            candidate = {"code": code, "name": name}
            current = mapping.get(key)
            if current and current != candidate:
                conflicts.add(key)
            else:
                mapping[key] = candidate

    for key in conflicts:
        mapping.pop(key, None)
    return mapping


def build_expansion_set_map(path: Path) -> dict[str, dict[str, str]]:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = _load_json(path)
    return parse_mtgjson_set_list(payload)


def _download_json(url: str, destination: Path, callback: Callable[[int | None], None] | None = None) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=120.0,
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length") or 0)
        written = 0
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            for chunk in response.iter_bytes(1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if callback:
                    callback(total and int(written / total * 100) or None)
    os.replace(temp_path, destination)
    return written


def iter_json_array(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[Any]:
    """Stream a top-level JSON array without loading the entire file into RAM."""
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as handle:
        buffer = ""
        position = 0
        started = False
        eof = False

        while True:
            if not eof and len(buffer) - position < 64 * 1024:
                chunk = handle.read(chunk_size)
                if chunk:
                    if position:
                        buffer = buffer[position:]
                        position = 0
                    buffer += chunk
                else:
                    eof = True

            while position < len(buffer) and buffer[position].isspace():
                position += 1

            if not started:
                if position >= len(buffer):
                    if eof:
                        return
                    continue
                if buffer[position] != "[":
                    raise ValueError(f"Expected a top-level JSON array in {path}.")
                position += 1
                started = True
                continue

            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if position < len(buffer) and buffer[position] == "]":
                return
            if position < len(buffer) and buffer[position] == ",":
                position += 1
                while position < len(buffer) and buffer[position].isspace():
                    position += 1

            if position >= len(buffer):
                if eof:
                    raise ValueError(f"Unexpected end of JSON array in {path}.")
                continue

            try:
                item, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                if eof:
                    raise
                chunk = handle.read(chunk_size)
                if not chunk:
                    eof = True
                else:
                    if position:
                        buffer = buffer[position:]
                        position = 0
                    buffer += chunk
                continue

            yield item
            position = end


def iter_jsonl(path: Path) -> Iterator[Any]:
    """Read plain or gzip-compressed newline-delimited JSON one object at a time."""
    with path.open("rb") as raw:
        magic = raw.read(2)
        raw.seek(0)
        binary = gzip.GzipFile(fileobj=raw) if magic == b"\x1f\x8b" else raw
        with io.TextIOWrapper(binary, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def _resolved_expansion(
    product: Product,
    expansion_map: dict[str, dict[str, str]],
    overrides: dict[str, str],
    supplemental_map: dict[str, dict[str, str]] | None = None,
    catalog_verified_map: dict[str, dict[str, str]] | None = None,
) -> tuple[str, str, str]:
    if product.expansion_id is not None:
        key = str(product.expansion_id)
        override = overrides.get(key)
        if override:
            return override, "Manual override", "override"
        mapped = expansion_map.get(key)
        if mapped:
            code = str(mapped.get("code") or "").strip()
            name = str(mapped.get("name") or "").strip()
            source = str(mapped.get("source") or "mtgjson")
            return code or name, name, source
        if supplemental_map:
            mapped = supplemental_map.get(key)
            if mapped:
                code = str(mapped.get("code") or "").strip()
                name = str(mapped.get("name") or "").strip()
                return code or name, name, "external_csv"
        if catalog_verified_map:
            mapped = catalog_verified_map.get(key)
            if mapped:
                code = str(mapped.get("code") or "").strip()
                name = str(mapped.get("name") or "").strip()
                return code or name, name, "catalog_verified"
    if product.expansion_id is None:
        return "UNKNOWN", "", "unmapped"
    return f"ID:{product.expansion_id}", "", "unmapped"


def _price_block(price: PriceGuide | None) -> dict[str, float | None]:
    if price is None:
        return {"low": None, "trend": None, "avg7": None, "avg30": None}
    return {
        "low": float(price.low) if price.low is not None else None,
        "trend": float(price.trend) if price.trend is not None else None,
        "avg7": float(price.avg7) if price.avg7 is not None else None,
        "avg30": float(price.avg30) if price.avg30 is not None else None,
    }


def merge_data(
    products: dict[int, Product],
    prices: dict[int, PriceGuide],
    expansion_map: dict[str, dict[str, str]],
    overrides: dict[str, str],
    supplemental_map: dict[str, dict[str, str]] | None = None,
    catalog_verified_map: dict[str, dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[int]]:
    rows: list[dict[str, Any]] = []
    unmapped: set[int] = set()
    resolved_products: dict[int, tuple[str, str, str]] = {}
    duplicate_counts: dict[tuple[str, str], int] = {}
    for product_id, product in products.items():
        if product_id not in prices:
            continue
        resolution = _resolved_expansion(
            product, expansion_map, overrides, supplemental_map, catalog_verified_map
        )
        resolved_products[product_id] = resolution
        expansion_code = resolution[0]
        key = (normalize_name(product.name), normalize_name(expansion_code))
        duplicate_counts[key] = duplicate_counts.get(key, 0) + 1

    for product_id, price in prices.items():
        product = products.get(product_id)
        if product is None:
            continue
        expansion_code, expansion_name, mapping_source = resolved_products.get(
            product_id, _resolved_expansion(
                product, expansion_map, overrides, supplemental_map, catalog_verified_map
            )
        )
        if mapping_source == "unmapped" and product.expansion_id is not None:
            unmapped.add(product.expansion_id)
        nonfoil_price = _price_block(price)
        key = (normalize_name(product.name), normalize_name(expansion_code))
        variant_count = duplicate_counts.get(key, 1)
        ambiguous = variant_count > 1
        ambiguity_reason = (
            f"Cardmarket has {variant_count} variants for this card and expansion, "
            "so the displayed price may not match the exact printing/art variant."
            if ambiguous else ""
        )
        foil_price = {
            "low": float(price.low_foil) if price.low_foil is not None else None,
            "trend": float(price.trend_foil) if price.trend_foil is not None else None,
            "avg7": float(price.avg7_foil) if price.avg7_foil is not None else None,
            "avg30": float(price.avg30_foil) if price.avg30_foil is not None else None,
        }
        foil_exists = any(value is not None for value in foil_price.values())
        rows.append(
            {
                "product_id": product_id,
                "card_name": product.name,
                "expansion_id": product.expansion_id,
                "expansion": expansion_code,
                "expansion_name": expansion_name,
                "mapping_source": mapping_source,
                "ambiguous": ambiguous,
                "ambiguity_reason": ambiguity_reason,
                "variant_count": variant_count,
                "nonfoil": nonfoil_price,
                "foil": foil_price if foil_exists else None,
                "cardmarket_url": f"https://www.cardmarket.com/en/Magic/Products?idProduct={product_id}",
            }
        )
    rows.sort(key=lambda row: (normalize_name(row["card_name"]), str(row["expansion"]), row["product_id"]))
    return rows, sorted(unmapped)


def write_merged(rows: list[dict[str, Any]], generated_at: str) -> None:
    payload = {
        "generated_at": generated_at,
        "source": {
            "price_guide": CARDMARKET_PRICE_GUIDE_URL,
            "product_list": CARDMARKET_PRODUCT_LIST_URL,
            "expansion_mapping": "MTGJSON mcmId/mcmIdExtras → set code, bundled expansion_map.csv fallback, then verified catalog anchors",
        },
        "row_count": len(rows),
        "rows": rows,
    }
    _atomic_write_json(MERGED_JSON_FILE, payload)

    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=MERGED_DIR, delete=False) as handle:
        temp_path = Path(handle.name)
        writer = csv.writer(handle)
        writer.writerow([
            "card_name", "expansion", "expansion_name", "product_id", "nonfoil_low",
            "nonfoil_trend", "nonfoil_avg7", "nonfoil_avg30", "foil_low", "foil_trend",
            "foil_avg7", "foil_avg30", "cardmarket_url",
        ])
        for row in rows:
            nonfoil = row["nonfoil"]
            foil = row["foil"] or {}
            writer.writerow([
                row["card_name"], row["expansion"], row["expansion_name"], row["product_id"],
                nonfoil["low"], nonfoil["trend"], nonfoil["avg7"], nonfoil["avg30"],
                foil.get("low"), foil.get("trend"), foil.get("avg7"), foil.get("avg30"),
                row["cardmarket_url"],
            ])
    os.replace(temp_path, MERGED_CSV_FILE)


try:
    APP_TIMEZONE = ZoneInfo("Europe/Warsaw")
except ZoneInfoNotFoundError:
    # Keep the scheduler usable on Windows installations that do not have
    # the optional IANA tzdata package installed.
    APP_TIMEZONE = datetime.now().astimezone().tzinfo


def is_stale() -> bool:
    """Return whether the local data predates the most recent 04:00 refresh window."""
    from datetime import timedelta

    if not MERGED_JSON_FILE.exists() or not STATUS_FILE.exists():
        return True
    try:
        status = _load_json(STATUS_FILE)
        updated_at = datetime.fromisoformat(str(status["updated_at"]).replace("Z", "+00:00"))
        local_now = datetime.now(APP_TIMEZONE)
        latest_refresh = local_now.replace(hour=4, minute=0, second=0, microsecond=0)
        if local_now < latest_refresh:
            latest_refresh -= timedelta(days=1)
        return updated_at.astimezone(APP_TIMEZONE) < latest_refresh
    except (KeyError, ValueError, TypeError, OSError):
        return True


def read_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {
            "state": "never_updated",
            "updated_at": None,
            "row_count": 0,
            "mapped_expansion_ids": 0,
            "unmapped_expansion_ids": [],
            "message": "No local Cardmarket data has been generated yet.",
        }
    try:
        return _load_json(STATUS_FILE)
    except (OSError, json.JSONDecodeError):
        return {
            "state": "error",
            "updated_at": None,
            "row_count": 0,
            "mapped_expansion_ids": 0,
            "unmapped_expansion_ids": [],
            "message": "The local Cardmarket status file could not be read.",
        }


def _legacy_avg7_by_product() -> dict[int, tuple[float | None, float | None]]:
    global _LEGACY_AVG7_CACHE_MTIME_NS, _LEGACY_AVG7_CACHE
    if not PRICE_GUIDE_FILE.exists():
        return {}
    mtime = PRICE_GUIDE_FILE.stat().st_mtime_ns
    if mtime == _LEGACY_AVG7_CACHE_MTIME_NS:
        return _LEGACY_AVG7_CACHE
    prices = load_prices()
    _LEGACY_AVG7_CACHE = {
        product_id: (
            float(price.avg7) if price.avg7 is not None else None,
            float(price.avg7_foil) if price.avg7_foil is not None else None,
        )
        for product_id, price in prices.items()
    }
    _LEGACY_AVG7_CACHE_MTIME_NS = mtime
    return _LEGACY_AVG7_CACHE


def load_merged_rows() -> list[dict[str, Any]]:
    if not MERGED_JSON_FILE.exists():
        return []
    payload = _load_json(MERGED_JSON_FILE)
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []

    # v24 snapshots did not persist avg7 yet. Read that value from the local raw
    # price guide only, with no network access, so the new display works immediately.
    if rows and isinstance(rows[0], dict) and "avg7" not in (rows[0].get("nonfoil") or {}):
        fallback = _legacy_avg7_by_product()
        for row in rows:
            product_id = _as_int(row.get("product_id"))
            if product_id is None:
                continue
            nonfoil_avg7, foil_avg7 = fallback.get(product_id, (None, None))
            row.setdefault("nonfoil", {})["avg7"] = nonfoil_avg7
            if isinstance(row.get("foil"), dict):
                row["foil"]["avg7"] = foil_avg7
    return rows


class LocalCardmarketIndex:
    """Read-only local index for Hareruya result enrichment."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mtime_ns: int | None = None
        self._by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def _refresh_if_needed(self) -> None:
        if not MERGED_JSON_FILE.exists():
            self._by_key = {}
            self._mtime_ns = None
            return
        mtime = MERGED_JSON_FILE.stat().st_mtime_ns
        if mtime == self._mtime_ns:
            return
        rows = load_merged_rows()
        index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (normalize_name(str(row.get("card_name", ""))), normalize_name(str(row.get("expansion", ""))))
            if key[0] and key[1]:
                index.setdefault(key, []).append(row)
        self._by_key = index
        self._mtime_ns = mtime

    def lookup(self, card_name: str, expansion: str, foil: bool = False) -> dict[str, Any] | None:
        with self._lock:
            self._refresh_if_needed()
            candidates = self._by_key.get((normalize_name(card_name), normalize_name(expansion)), [])
            if not candidates:
                return None
            price_key = "foil" if foil else "nonfoil"
            for row in candidates:
                data = row.get(price_key)
                if isinstance(data, dict) and any(value is not None for value in data.values()):
                    return row
            return candidates[0]


LOCAL_INDEX = LocalCardmarketIndex()


def download_and_merge(progress: ProgressCallback | None = None) -> dict[str, Any]:
    _ensure_dirs()
    progress = progress or (lambda _pct, _message: None)
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    progress(5, "Downloading Cardmarket product catalog…")
    _download_json(CARDMARKET_PRODUCT_LIST_URL, PRODUCT_LIST_FILE)
    progress(25, "Downloading Cardmarket price guide…")
    _download_json(CARDMARKET_PRICE_GUIDE_URL, PRICE_GUIDE_FILE)

    products = load_products()
    prices = load_prices()
    if not products or not prices:
        raise RuntimeError(
            f"Cardmarket download produced no usable records (products={len(products):,}, prices={len(prices):,})."
        )
    progress(42, f"Loaded {len(products):,} products and {len(prices):,} price records.")

    # This is the persistent set-map build. It deliberately happens before
    # the merged table is written, so the reference file exists even if a
    # later step fails. MTGJSON SetList provides mcmId/mcmIdExtras -> code.
    previous_map = load_expansion_set_map()
    try:
        progress(48, "Downloading MTGJSON expansion map…")
        _download_json(MTGJSON_SET_LIST_URL, MTGJSON_SET_LIST_FILE)
        expansion_map = build_expansion_set_map(MTGJSON_SET_LIST_FILE)
        if not expansion_map:
            raise RuntimeError("MTGJSON SetList did not contain any Cardmarket set IDs.")
        map_generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _atomic_write_json(EXPANSION_SET_MAP_FILE, expansion_map)
        _atomic_write_json(EXPANSION_SET_MAP_STATUS_FILE, {
            "source": MTGJSON_SET_LIST_URL,
            "updated_at": map_generated_at,
            "mapped_expansion_ids": len(expansion_map),
        })
    except Exception as exc:
        expansion_map = previous_map
        if expansion_map:
            progress(65, f"Using previous local expansion map because the latest map refresh failed: {exc}")
        else:
            progress(65, f"No expansion map is available; unmapped Cardmarket IDs will be retained: {exc}")
    finally:
        MTGJSON_SET_LIST_FILE.unlink(missing_ok=True)

    overrides = load_expansion_overrides()
    supplemental_map = load_supplemental_expansion_map()
    catalog_verified_map = load_catalog_verified_expansion_map()

    progress(78, "Merging Cardmarket prices with the singles catalog…")
    rows, row_unmapped = merge_data(
        products, prices, expansion_map, overrides, supplemental_map, catalog_verified_map
    )
    catalog_expansion_ids = {
        product.expansion_id
        for product in products.values()
        if product.expansion_id is not None
    }
    unresolved_catalog_ids = {
        expansion_id
        for expansion_id in catalog_expansion_ids
        if str(expansion_id) not in expansion_map
        and str(expansion_id) not in supplemental_map
        and str(expansion_id) not in catalog_verified_map
        and str(expansion_id) not in overrides
    }
    unmapped = sorted(set(row_unmapped) | unresolved_catalog_ids)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_merged(rows, generated_at)
    _atomic_write_json(UNMAPPED_FILE, {
        "updated_at": generated_at,
        "expansion_ids": unmapped,
        "product_expansion_count": len(catalog_expansion_ids),
        "mapped_product_expansion_count": len(catalog_expansion_ids) - len(unresolved_catalog_ids),
    })

    mapped_ids = len(catalog_expansion_ids) - len(unresolved_catalog_ids)
    status = {
        "state": "ready",
        "started_at": started_at,
        "updated_at": generated_at,
        "row_count": len(rows),
        "mapped_expansion_ids": mapped_ids,
        "unmapped_expansion_ids": unmapped,
        "expansion_map_count": len(expansion_map),
        "supplemental_expansion_map_count": len(supplemental_map),
        "catalog_verified_expansion_map_count": len(catalog_verified_map),
        "combined_expansion_map_count": len(set(expansion_map) | set(supplemental_map) | set(catalog_verified_map)),
        "product_count": len(products),
        "price_count": len(prices),
        "message": "Local Cardmarket price data is ready.",
    }
    _atomic_write_json(STATUS_FILE, status)
    progress(100, f"Finished. {len(rows):,} merged rows are available locally.")
    return status
