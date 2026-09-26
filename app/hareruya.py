from __future__ import annotations

import os
import re
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.hareruyamtg.com/en/products/search"
LOADER_IMAGE_URL = "https://www.hareruyamtg.com/en/assets/img/ajax-loader.gif"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
PRICE_RE = re.compile(r"(?:¥|￥)\s*([0-9][0-9,]*)|([0-9][0-9,]*)\s*(?:JPY|円)\b", re.I)
STOCK_RE = re.compile(r"\b(?:NM|SP|MP|HP)\s+Stock\s*[:：]\s*(\d+)\b", re.I)
PAGE_RE = re.compile(r"(?:Page|ページ)\s*\d+\s*/\s*(\d+)", re.I)
LANGUAGE_RE = re.compile(r"[【〖]\s*(JP|EN|CS|CT|FR|DE|IT|KO|PT|RU|ES|AG)\s*[】〗]", re.I)
EXPANSION_RE = re.compile(r"\[([^\[\]]+)\]\s*$")


@dataclass(frozen=True)
class Listing:
    price: int
    language: str
    expansion: str
    foil: bool
    title: str
    stock: int
    url: str
    image_url: str


@dataclass(frozen=True)
class CardResult:
    card_name: str
    rows: list[Listing]
    error: str | None = None


class HareruyaError(RuntimeError):
    pass


def clean(text: str) -> str:
    return " ".join(text.split())


NAME_BLOCK_RE = re.compile(r"《([^》]+)》")


def contains_card(title: str, card_name: str) -> bool:
    normalize = lambda value: clean(unicodedata.normalize("NFKC", value)).casefold()
    wanted = normalize(card_name)
    title_normalized = normalize(title)

    name_blocks = NAME_BLOCK_RE.findall(title)
    if name_blocks:
        for block in name_blocks:
            for name in re.split(r"[/／]", block):
                if normalize(name) == wanted:
                    return True
        return False

    # Conservative fallback for older/plain test markup without 《…》 blocks.
    return bool(re.match(rf"^{re.escape(wanted)}(?=$|[\s【〖\[(])", title_normalized))


def search_url(card_name: str) -> str:
    return f"{BASE_URL}?suggest_type=all&product={quote(card_name)}"


def page_url(base_url: str, number: int) -> str:
    parts = urlsplit(base_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
    query.append(("page", str(number)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def total_pages(soup: BeautifulSoup) -> int:
    boxes = soup.select(".result_pagenum")
    if not boxes:
        return 1
    pages = [int(match.group(1)) for box in boxes for match in PAGE_RE.finditer(clean(box.get_text(" ", strip=True)))]
    return max(pages, default=1)


def wait_for_details(page) -> None:
    page.wait_for_function(
        """() => {
            const items = [...document.querySelectorAll('.itemData')];
            if (!items.length) return false;
            return items.every(item =>
                item.querySelector('.itemDetail__price')?.textContent.trim() &&
                item.querySelector('.itemDetail__stock')?.textContent.trim()
            );
        }""",
        timeout=5000,
    )


def trigger_lazy_loading(page) -> None:
    page.evaluate(
        """async () => {
            for (const item of document.querySelectorAll('.itemData')) {
                item.scrollIntoView({block: 'center'});
                await new Promise(resolve => setTimeout(resolve, 40));
            }
            window.scrollTo(0, 0);
        }"""
    )


def _contains_loader_image(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    loader = LOADER_IMAGE_URL.casefold()
    for node in soup.select("img, source"):
        for attr in ("src", "current-src", "data-src", "data-lazy-src", "data-original", "data-image", "data-image-url", "data-lazy", "data-bg", "data-background"):
            value = node.get(attr)
            if value and loader in urljoin(BASE_URL, value).casefold():
                return True
        srcset = node.get("srcset") or node.get("data-srcset") or ""
        if loader in srcset.casefold():
            return True
    for node in soup.select("[style]"):
        if loader in node.get("style", "").casefold():
            return True
    return False


def load_search_page(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".itemData", state="attached", timeout=20000)
        try:
            wait_for_details(page)
        except PlaywrightTimeoutError:
            trigger_lazy_loading(page)
            wait_for_details(page)

        html = page.content()
        # Hareruya can temporarily expose ajax-loader.gif as the product image
        # while its real image is being populated. Give the page 3 seconds,
        # then 2 more seconds, re-triggering lazy loading before each check.
        for delay in (3, 2):
            if not _contains_loader_image(html):
                break
            time.sleep(delay)
            trigger_lazy_loading(page)
            html = page.content()
        return html
    except PlaywrightTimeoutError as exc:
        raise HareruyaError(
            "Hareruya loaded listings but did not populate all price/stock fields in time."
        ) from exc


def extract_title(item) -> str:
    node = item.select_one("a.itemName")
    return clean(node.get_text(" ", strip=True)) if node else ""


def extract_price(item) -> int | None:
    node = item.select_one(".itemDetail__price")
    if not node:
        return None
    match = PRICE_RE.search(clean(node.get_text(" ", strip=True)))
    if not match:
        return None
    return int(next(group for group in match.groups() if group is not None).replace(",", ""))


def extract_stock(item) -> int:
    node = item.select_one(".itemDetail__stock")
    if not node:
        return 0
    return max((int(match.group(1)) for match in STOCK_RE.finditer(clean(node.get_text(" ", strip=True)))), default=0)


IMAGE_URL_RE = re.compile(
    r"(?:https?:)?//[^\"'\s)]+(?:\.(?:jpe?g|png|webp|gif)(?:\?[^\"'\s)]*)?)",
    re.I,
)


def _normalise_image_candidate(value: str) -> str:
    value = value.strip().strip("\"'")
    if not value or value.startswith("data:"):
        return ""
    # CSS background-image values often look like: url("/path/card.jpg").
    value = re.sub(r"^url\((.*?)\)$", r"\1", value, flags=re.I).strip().strip("\"'")
    candidate = urljoin(BASE_URL, value)
    if candidate.casefold() == LOADER_IMAGE_URL.casefold():
        return ""
    return candidate


def extract_image_url(item) -> str:
    """Extract the product image from Hareruya's rendered listing markup.

    Hareruya has used several image-loading patterns over time, including lazy
    data attributes, srcset, CSS background images, and image URLs embedded in
    rendered markup. Try all of them rather than depending on one selector.
    """
    attr_names = (
        "src", "current-src", "data-src", "data-lazy-src", "data-original",
        "data-image", "data-image-url", "data-lazy", "data-bg", "data-background",
    )

    for node in item.select("img, source"):
        for attr in attr_names:
            value = node.get(attr)
            if value:
                candidate = _normalise_image_candidate(value)
                if candidate:
                    return candidate
        srcset = node.get("srcset") or node.get("data-srcset")
        if srcset:
            # Prefer the last/largest candidate in srcset.
            candidates = [part.strip().split(" ")[0] for part in srcset.split(",") if part.strip()]
            if candidates:
                candidate = _normalise_image_candidate(candidates[-1])
                if candidate:
                    return candidate

    for node in item.select("[style]"):
        style = node.get("style", "")
        match = re.search(r"background-image\s*:\s*url\(([^)]+)\)", style, re.I)
        if match:
            candidate = _normalise_image_candidate(match.group(1))
            if candidate:
                return candidate

    # Some versions of the result markup keep the image beside .itemData
    # rather than inside it. Walk up only through containers that contain one
    # listing, so we do not accidentally pick an adjacent card's image.
    ancestor = item.parent
    for _ in range(3):
        if ancestor is None:
            break
        if len(ancestor.select(".itemData")) == 1:
            for node in ancestor.select("img, source"):
                for attr in attr_names:
                    value = node.get(attr)
                    if value:
                        candidate = _normalise_image_candidate(value)
                        if candidate:
                            return candidate
                srcset = node.get("srcset") or node.get("data-srcset")
                if srcset:
                    candidates = [part.strip().split(" ")[0] for part in srcset.split(",") if part.strip()]
                    if candidates:
                        candidate = _normalise_image_candidate(candidates[-1])
                        if candidate:
                            return candidate
            for node in ancestor.select("[style]"):
                match = re.search(r"background-image\s*:\s*url\(([^)]+)\)", node.get("style", ""), re.I)
                if match:
                    candidate = _normalise_image_candidate(match.group(1))
                    if candidate:
                        return candidate
            for match in IMAGE_URL_RE.finditer(str(ancestor)):
                candidate = _normalise_image_candidate(match.group(0))
                if candidate:
                    return candidate
        ancestor = ancestor.parent

    # Final fallback: look for an absolute image URL in this listing's markup.
    for match in IMAGE_URL_RE.finditer(str(item)):
        candidate = _normalise_image_candidate(match.group(0))
        if candidate:
            return candidate

    return ""


def parse_page(html: str) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".itemData")
    if not items:
        raise HareruyaError("The rendered page contains no .itemData elements.")

    rows: list[Listing] = []
    for item in items:
        title = extract_title(item)
        price = extract_price(item)
        if not title or price is None:
            continue
        if "art card" in title.casefold():
            continue
        language_match = LANGUAGE_RE.search(title)
        expansion_match = EXPANSION_RE.search(title)
        link = item.select_one("a.itemName")
        listing_url = urljoin(BASE_URL, link.get("href", "")) if link and link.get("href") else ""
        rows.append(
            Listing(
                price=price,
                language=language_match.group(1).upper() if language_match else "Unknown",
                expansion=expansion_match.group(1).strip() if expansion_match else "Unknown",
                foil=bool(re.search(r"\bfoil\b", title, re.I) or "retrof" in title.casefold()),
                title=title,
                stock=extract_stock(item),
                url=listing_url,
                image_url=extract_image_url(item),
            )
        )
    return rows, total_pages(soup)


def crawl(card_name: str, page) -> list[Listing]:
    base_url = search_url(card_name)
    html = load_search_page(page, base_url)
    rows, pages = parse_page(html)
    # Protect the server from unexpectedly huge searches.
    max_pages = int(os.getenv("HARERUYA_MAX_PAGES", "20"))
    for number in range(2, min(pages, max_pages) + 1):
        html = load_search_page(page, page_url(base_url, number))
        page_rows, _ = parse_page(html)
        rows.extend(page_rows)
    return rows


def select_rows(rows: list[Listing], card_name: str, finish: str) -> list[Listing]:
    selected = [row for row in rows if contains_card(row.title, card_name)]
    if finish == "foil":
        selected = [row for row in selected if row.foil]
    elif finish == "nonfoil":
        selected = [row for row in selected if not row.foil]
    return sorted((row for row in selected if row.stock > 0), key=lambda row: row.price)


def check_card(card_name: str, finish: str, playwright, browser) -> CardResult:
    context = browser.new_context(user_agent=USER_AGENT, locale="en-US")
    page = context.new_page()
    try:
        rows = select_rows(crawl(card_name, page), card_name, finish)
        return CardResult(card_name, rows)
    except HareruyaError as exc:
        return CardResult(card_name, [], str(exc))
    except Exception as exc:
        return CardResult(card_name, [], f"Unexpected error: {exc}")
    finally:
        context.close()


def run_cards(card_names: list[str], finish: str, progress=None, worker_count: int | None = None) -> list[CardResult]:
    """Run bounded concurrent Playwright workers and preserve input order."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    names = [clean(name) for name in card_names if clean(name)]
    if not names:
        return []
    max_workers = worker_count or min(4, len(names))
    results: list[CardResult | None] = [None] * len(names)
    lock = threading.Lock()
    completed = 0

    def worker(index: int, card_name: str) -> tuple[int, CardResult]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                return index, check_card(card_name, finish, playwright, browser)
            finally:
                browser.close()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, i, name) for i, name in enumerate(names)]
        for future in as_completed(futures):
            index, result = future.result()
            results[index] = result
            with lock:
                completed += 1
                current = completed
            if progress:
                progress(current, len(names))

    return [result for result in results if result is not None]
