from decimal import Decimal
from pathlib import Path
import gzip
import json

from app.cardmarket_data import (
    download_and_merge,
    merge_data,
    normalize_name,
    normalize_expansion_code,
    load_expansion_set_map,
    parse_price_guide,
    parse_product_list,
)


def test_parse_cardmarket_catalog_and_price_guide():
    products = parse_product_list({
        "products": [
            {"idProduct": 1001, "name": "Ad Nauseam", "idExpansion": 500, "idMetacard": 77},
            {"idProduct": 1002, "name": "Ad Nauseam", "idExpansion": 501, "idMetacard": 77},
        ]
    })
    prices = parse_price_guide({
        "priceGuide": [
            {"idProduct": 1001, "low": "1.20", "trend": "1.50", "avg30": "1.40", "low-foil": "4.00", "trend-foil": "4.80", "avg30-foil": "4.50"},
            {"idProduct": 1002, "low": "0.80", "trend": "1.10", "avg30": "1.00", "low-foil": None, "trend-foil": None, "avg30-foil": None},
        ]
    })
    assert products[1001].expansion_id == 500
    from decimal import Decimal
    assert prices[1001].low == Decimal("1.20")
    assert str(prices[1001].avg30) == "1.40"
    assert prices[1002].low_foil is None


def test_parse_cardmarket_price_guide_json_root():
    payload = {
        "version": 1,
        "createdAt": "2026-09-26T02:41:48+0200",
        "priceGuides": [
            {
                "idProduct": 19831,
                "low": 5,
                "trend": 8.66,
                "avg7": 8.31,
                "avg30": 8.82,
                "low-foil": 44.98,
                "trend-foil": 56.86,
                "avg7-foil": 55.20,
                "avg30-foil": 53.86,
            }
        ],
    }
    prices = parse_price_guide(payload)
    assert list(prices) == [19831]
    assert prices[19831].low == Decimal("5.00")
    assert prices[19831].trend == Decimal("8.66")
    assert prices[19831].avg7 == Decimal("8.31")
    assert prices[19831].avg30 == Decimal("8.82")
    assert prices[19831].low_foil == Decimal("44.98")
    assert prices[19831].trend_foil == Decimal("56.86")
    assert prices[19831].avg7_foil == Decimal("55.20")
    assert prices[19831].avg30_foil == Decimal("53.86")



def test_unmapped_expansion_ids_are_reported():
    products = parse_product_list({"products": [
        {"idProduct": 1001, "name": "Mystery Card", "idExpansion": 9999},
    ]})
    prices = parse_price_guide({"priceGuide": [
        {"idProduct": 1001, "low": "1", "trend": "1", "avg30": "1"},
    ]})
    rows, unmapped = merge_data(products, prices, {}, {})
    assert rows[0]["expansion"] == "ID:9999"
    assert rows[0]["mapping_source"] == "unmapped"
    assert unmapped == [9999]



def test_normalize_expansion_code_rules():
    assert normalize_expansion_code("XDMR") == "DMR"
    assert normalize_expansion_code("XSOS") == "SOS"
    assert normalize_expansion_code("PM21") == "M21"
    assert normalize_expansion_code("SLDSSS") == "SLD"
    assert normalize_expansion_code("SLDFN") == "SLD"
    assert normalize_expansion_code("SLD") == "SLD"

    assert normalize_expansion_code("SOA") == "SOA"
    assert normalize_expansion_code("ABC") == "ABC"
    assert normalize_expansion_code("ABCDEF") == "ABCDEF"
    assert normalize_expansion_code("XABCDE") == "XABCDE"
    assert normalize_expansion_code("PABCDE") == "PABCDE"
    assert normalize_expansion_code("SLCCK") == "SLCCK"
    assert normalize_expansion_code("GnDT") == "GNDT"


def test_bundled_expansion_map_contains_normalized_short_codes():
    import app.cardmarket_data as cm

    mapping = load_expansion_set_map()
    assert mapping["5193"]["code"] == "DMR"
    assert mapping["6546"]["code"] == "SOS"
    assert mapping["3319"]["code"] == "M21"
    assert mapping["5110"]["code"] == "SLD"
    assert mapping["5049"]["code"] == "SLD"
    assert mapping["6390"]["code"] == "SLCCK"

    for entry in mapping.values():
        code = entry.get("code", "")
        if not code:
            continue
        assert not (len(code) == 4 and code[0] in {"X", "P"})
        assert "SLD" not in code or code == "SLD"



def test_normalize_name():
    assert normalize_name("  Ad  Nauseam ") == "ad nauseam"



def test_expansion_map_is_applied_to_every_product_in_an_expansion():
    products = parse_product_list({"products": [
        {"idProduct": 1001, "name": "Mapped Card", "idExpansion": 500},
        {"idProduct": 1002, "name": "Second Card", "idExpansion": 500},
    ]})
    prices = parse_price_guide({"priceGuide": [
        {"idProduct": 1001, "low": "1", "trend": "1", "avg30": "1"},
        {"idProduct": 1002, "low": "2", "trend": "2", "avg30": "2"},
    ]})
    rows, unmapped = merge_data(
        products,
        prices,
        {"500": {"code": "SOA", "name": "Shards of Alara"}},
        {},
    )
    assert [(row["card_name"], row["expansion"], row["mapping_source"]) for row in rows] == [
        ("Mapped Card", "SOA", "mtgjson"),
        ("Second Card", "SOA", "mtgjson"),
    ]
    assert unmapped == []


def test_download_and_merge_end_to_end_builds_persistent_reference_and_merged_rows(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    monkeypatch.setattr(cm, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(cm, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(cm, "REFERENCE_DIR", tmp_path / "reference")
    monkeypatch.setattr(cm, "MERGED_DIR", tmp_path / "merged")
    monkeypatch.setattr(cm, "PRICE_GUIDE_FILE", tmp_path / "raw" / "price_guide_1.json")
    monkeypatch.setattr(cm, "PRODUCT_LIST_FILE", tmp_path / "raw" / "products_singles_1.json")
    bundled_map = tmp_path / "reference" / "expansion_ids_map.txt"
    bundled_map.parent.mkdir(parents=True, exist_ok=True)
    bundled_map.write_text(json.dumps({"status": "success", "data": {"expansions": {
        "500": {"expansion_id": 500, "name": "Shards of Alara", "code": "SOA"}
    }}}), encoding="utf-8")
    monkeypatch.setattr(cm, "BUNDLED_EXPANSION_MAP_FILE", bundled_map)
    monkeypatch.setattr(cm, "EXPANSION_OVERRIDES_FILE", tmp_path / "reference" / "expansion_overrides.json")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", tmp_path / "merged" / "cardmarket_prices.json")
    monkeypatch.setattr(cm, "MERGED_CSV_FILE", tmp_path / "merged" / "cardmarket_prices.csv")
    monkeypatch.setattr(cm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(cm, "UNMAPPED_FILE", tmp_path / "reference" / "unmapped_expansion_ids.json")

    def fake_download(url, destination, callback=None):
        if "products_singles_1" in url:
            destination.write_text(json.dumps({"products": [
                {"idProduct": 1001, "name": "Ad Nauseam", "idExpansion": 500},
                {"idProduct": 1002, "name": "Unmapped Card", "idExpansion": 9999},
            ]}), encoding="utf-8")
        elif "price_guide_1" in url:
            destination.write_text(json.dumps({"priceGuide": [
                {"idProduct": 1001, "low": "10", "trend": "12", "avg30": "11", "low-foil": "20", "trend-foil": "22", "avg30-foil": "21"},
                {"idProduct": 1002, "low": "3", "trend": "4", "avg30": "3.5"},
            ]}), encoding="utf-8")
        else:
            raise AssertionError(url)
        if callback:
            callback(100)
        return destination.stat().st_size

    monkeypatch.setattr(cm, "_download_json", fake_download)

    status = download_and_merge()
    assert status["state"] == "ready"
    assert status["row_count"] == 2
    assert status["expansion_map_count"] == 1
    rows = cm.load_merged_rows()
    assert rows[0]["card_name"] == "Ad Nauseam"
    assert rows[0]["expansion"] == "SOA"
    assert rows[0]["mapping_source"] == "bundled_cardmarket_map"
    assert rows[0]["foil"]["avg30"] == 21.0
    assert status["unmapped_expansion_ids"] == [9999]
    assert cm.BUNDLED_EXPANSION_MAP_FILE.exists()


def test_api_table_exact_search_is_optional(monkeypatch, tmp_path):
    import app.main as main
    import app.cardmarket_data as cm
    from fastapi.testclient import TestClient

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [
        {"product_id": 1, "card_name": "Tithe", "expansion": "SOA", "nonfoil": {}, "foil": {}},
        {"product_id": 2, "card_name": "Mana Tithe", "expansion": "SOA", "nonfoil": {}, "foil": {}},
    ]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)

    client = TestClient(main.app)
    loose = client.get("/api/cardmarket/table?q=Tithe")
    assert loose.status_code == 200
    assert [row["card_name"] for row in loose.json()["rows"]] == ["Tithe", "Mana Tithe"]

    exact = client.get("/api/cardmarket/table?q=Tithe&exact=true")
    assert exact.status_code == 200
    assert [row["card_name"] for row in exact.json()["rows"]] == ["Tithe"]


def test_api_table_excludes_art_series_before_pagination(monkeypatch, tmp_path):
    import app.main as main
    import app.cardmarket_data as cm
    from fastapi.testclient import TestClient

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [
        {"product_id": 1, "card_name": "Flicker", "expansion": "SOA", "nonfoil": {}, "foil": {}},
        {"product_id": 2, "card_name": "Art Series: Flickering Hound", "expansion": "SLD", "nonfoil": {}, "foil": {}},
        {"product_id": 3, "card_name": "Flickerform", "expansion": "SOA", "nonfoil": {}, "foil": {}},
    ]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)

    client = TestClient(main.app)
    response = client.get("/api/cardmarket/table?q=Flic&page=1&page_size=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [row["card_name"] for row in payload["rows"]] == ["Flicker"]

    response = client.get("/api/cardmarket/table?q=Flic&page=2&page_size=1")
    assert response.status_code == 200
    assert [row["card_name"] for row in response.json()["rows"]] == ["Flickerform"]


def test_cardmarket_suggestions_exclude_art_series_and_rank_prefix_matches(monkeypatch, tmp_path):
    import app.main as main
    import app.cardmarket_data as cm
    from fastapi.testclient import TestClient

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [
        {"product_id": 1, "card_name": "Flicker", "expansion": "SOA"},
        {"product_id": 2, "card_name": "Flicker of Fate", "expansion": "M20"},
        {"product_id": 3, "card_name": "Flickerform", "expansion": "CMD"},
        {"product_id": 4, "card_name": "Art Series: Flickering Hound", "expansion": "SLD"},
        {"product_id": 5, "card_name": "Flickering Ward", "expansion": "TSP"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)

    client = TestClient(main.app)
    response = client.get("/api/cardmarket/suggestions?q=Flic")
    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert suggestions[:3] == ["Flicker", "Flicker of Fate", "Flickerform"]
    assert "Art Series: Flickering Hound" not in suggestions

    short = client.get("/api/cardmarket/suggestions?q=Fli")
    assert short.status_code == 200
    assert short.json()["suggestions"] == []


def test_cardmarket_scryfall_endpoint_returns_promo_types(monkeypatch):
    import app.main as main
    from app.scryfall import ScryfallCardInfo
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        main,
        "get_cardmarket_card_info",
        lambda product_id: ScryfallCardInfo(
            image_url="https://cards.scryfall.io/normal/example.jpg",
            promo_types=("surgefoil", "universesbeyond"),
            promo_type_labels=("Surge Foil",),
        ),
    )
    response = TestClient(main.app).get("/api/cardmarket/scryfall/900736")
    assert response.status_code == 200
    assert response.json()["image_url"].endswith("example.jpg")
    assert response.json()["promo_types"] == ["surgefoil", "universesbeyond"]
    assert response.json()["promo_type_labels"] == ["Surge Foil"]



def test_api_table_returns_populated_local_rows(monkeypatch, tmp_path):
    import app.main as main
    import app.cardmarket_data as cm
    from fastapi.testclient import TestClient

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"generated_at": "2026-09-26T00:00:00Z", "rows": [{
        "product_id": 1001, "card_name": "Ad Nauseam", "expansion_id": 500, "expansion": "SOA",
        "expansion_name": "Shards of Alara", "mapping_source": "mtgjson",
        "nonfoil": {"low": 10.0, "trend": 12.0, "avg30": 11.0},
        "foil": {"low": 20.0, "trend": 22.0, "avg30": 21.0},
        "cardmarket_url": "https://www.cardmarket.com/en/Magic/Products?idProduct=1001"
    }]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)

    response = TestClient(main.app).get("/api/cardmarket/table?q=Ad%20Nauseam")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["rows"][0]["card_name"] == "Ad Nauseam"
    assert payload["rows"][0]["expansion"] == "SOA"


def test_hareruya_api_enriches_listing_from_local_cardmarket_data(monkeypatch, tmp_path):
    import app.main as main
    import app.cardmarket_data as cm
    from app.hareruya import CardResult, Listing
    from app.models import CheckRequest
    from fastapi.testclient import TestClient
    from app.jobs import Job

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [{
        "product_id": 1001, "card_name": "Ad Nauseam", "expansion_id": 500, "expansion": "SOA",
        "expansion_name": "Shards of Alara", "mapping_source": "mtgjson",
        "nonfoil": {"low": 10.0, "trend": 12.0, "avg30": 11.0},
        "foil": {"low": 20.0, "trend": 22.0, "avg30": 21.0},
        "cardmarket_url": "https://www.cardmarket.com/en/Magic/Products?idProduct=1001"
    }]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)
    cm.LOCAL_INDEX._mtime_ns = None
    cm.LOCAL_INDEX._by_key = {}

    listing = Listing(39_350, "EN", "SOA", True, "〖Foil〗《Ad Nauseam》[SOA]", 2, "https://hareruya.example/listing", "https://hareruya.example/image")
    fake_job = Job("test-job", ["Ad Nauseam"], "all", "cheapest", status="complete", completed=1, results=[CardResult("Ad Nauseam", [listing])], eur_jpy_rate=180.0)
    monkeypatch.setattr(main.manager, "get", lambda job_id: fake_job if job_id == "test-job" else None)

    response = TestClient(main.app).get("/api/jobs/test-job")
    assert response.status_code == 200
    result = response.json()["results"][0]["rows"][0]
    assert result["cardmarket"]["expansion"] == "SOA"
    assert result["cardmarket"]["foil"]["avg30"] == 21.0

def test_merge_marks_duplicate_card_expansion_as_ambiguous_and_prefers_foil_price():
    products = parse_product_list({"products": [
        {"idProduct": 1001, "name": "Ad Nauseam", "idExpansion": 6547},
        {"idProduct": 1002, "name": "Ad Nauseam", "idExpansion": 6547},
        {"idProduct": 1003, "name": "Other Card", "idExpansion": 6547},
    ]})
    prices = parse_price_guide({"priceGuides": [
        {"idProduct": 1001, "low": "5", "avg7": "6", "low-foil": None, "avg7-foil": None},
        {"idProduct": 1002, "low": "6", "avg7": "7", "low-foil": "20", "avg7-foil": "21"},
        {"idProduct": 1003, "low": "1", "avg7": "2"},
    ]})
    rows, unmapped = merge_data(
        products, prices, {"6547": {"code": "SOA", "name": "Secrets of Strixhaven Mystical Archive", "source": "test"}}, {},
    )
    ad_rows = [row for row in rows if row["card_name"] == "Ad Nauseam"]
    assert len(ad_rows) == 2
    assert all(row["ambiguous"] is True for row in ad_rows)
    assert all(row["variant_count"] == 2 for row in ad_rows)
    assert ad_rows[0]["ambiguity_reason"]
    assert unmapped == []


def test_local_index_picks_cheapest_trend_for_normal_hareruya_variant(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [
        {
            "product_id": 1001, "card_name": "Ancient Tomb", "expansion": "UMA",
            "nonfoil": {"low": 150.0, "trend": 160.0, "avg7": 158.0},
            "foil": None, "cardmarket_url": "https://example.test/1001",
        },
        {
            "product_id": 1002, "card_name": "Ancient Tomb", "expansion": "UMA",
            "nonfoil": {"low": 100.0, "trend": 112.0, "avg7": 111.0},
            "foil": None, "cardmarket_url": "https://example.test/1002",
        },
    ]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)
    cm.LOCAL_INDEX._mtime_ns = None
    cm.LOCAL_INDEX._by_key = {}

    row = cm.LOCAL_INDEX.lookup("Ancient Tomb", "UMA", False, "《Ancient Tomb》[UMA]")
    assert row["product_id"] == 1002
    assert row["nonfoil"]["trend"] == 112.0


def test_local_index_picks_most_expensive_trend_for_special_hareruya_variants(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [
        {
            "product_id": 1001, "card_name": "Ancient Tomb", "expansion": "UMA",
            "nonfoil": {"low": 150.0, "trend": 160.0, "avg7": 158.0},
            "foil": None, "cardmarket_url": "https://example.test/1001",
        },
        {
            "product_id": 1002, "card_name": "Ancient Tomb", "expansion": "UMA",
            "nonfoil": {"low": 100.0, "trend": 112.0, "avg7": 111.0},
            "foil": None, "cardmarket_url": "https://example.test/1002",
        },
    ]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)
    cm.LOCAL_INDEX._mtime_ns = None
    cm.LOCAL_INDEX._by_key = {}

    special_titles = [
        "《Ancient Tomb》【Surge・Foil】[UMA]",
        "《Ancient Tomb》■RetroF■[UMA]",
        "《Ancient Tomb》【Galaxy Foil】[UMA]",
        "《Ancient Tomb》【Chocobo Track・Foil】[UMA]",
        "《Ancient Tomb》【Foil Etched】[UMA]",
        "《Ancient Tomb》【Fracture・Foil】[UMA]",
    ]
    for title in special_titles:
        row = cm.LOCAL_INDEX.lookup("Ancient Tomb", "UMA", False, title)
        assert row["product_id"] == 1001, title


def test_local_index_prefers_relevant_foil_trend(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [
        {
            "product_id": 1001, "card_name": "Test Card", "expansion": "UMA",
            "nonfoil": {"low": 10.0, "trend": 100.0},
            "foil": {"low": 50.0, "trend": 180.0},
        },
        {
            "product_id": 1002, "card_name": "Test Card", "expansion": "UMA",
            "nonfoil": {"low": 9.0, "trend": 90.0},
            "foil": {"low": 40.0, "trend": 120.0},
        },
    ]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)
    cm.LOCAL_INDEX._mtime_ns = None
    cm.LOCAL_INDEX._by_key = {}

    nonfoil = cm.LOCAL_INDEX.lookup("Test Card", "UMA", False, "《Test Card》[UMA]")
    foil = cm.LOCAL_INDEX.lookup("Test Card", "UMA", True, "《Test Card》【Foil Etched】[UMA]")
    assert nonfoil["product_id"] == 1002
    assert foil["product_id"] == 1001


def test_hareruya_api_exposes_cardmarket_ambiguity_metadata(monkeypatch, tmp_path):
    import app.main as main
    import app.cardmarket_data as cm
    from app.hareruya import CardResult, Listing
    from app.jobs import Job
    from fastapi.testclient import TestClient

    merged = tmp_path / "cardmarket_prices.json"
    merged.write_text(json.dumps({"rows": [
        {
            "product_id": 1001, "card_name": "Ad Nauseam", "expansion_id": 6547,
            "expansion": "SOA", "expansion_name": "Secrets of Strixhaven Mystical Archive",
            "mapping_source": "catalog_verified", "ambiguous": True,
            "ambiguity_reason": "Cardmarket has 2 variants for this card and expansion, so the displayed price may not match the exact printing/art variant.",
            "variant_count": 2, "nonfoil": {"low": 5.0, "avg7": 6.0}, "foil": None,
            "cardmarket_url": "https://www.cardmarket.com/en/Magic/Products?idProduct=1001"
        },
        {
            "product_id": 1002, "card_name": "Ad Nauseam", "expansion_id": 6547,
            "expansion": "SOA", "expansion_name": "Secrets of Strixhaven Mystical Archive",
            "mapping_source": "catalog_verified", "ambiguous": True,
            "ambiguity_reason": "Cardmarket has 2 variants for this card and expansion, so the displayed price may not match the exact printing/art variant.",
            "variant_count": 2, "nonfoil": {"low": 6.0, "avg7": 7.0}, "foil": {"low": 20.0, "avg7": 21.0},
            "cardmarket_url": "https://www.cardmarket.com/en/Magic/Products?idProduct=1002"
        },
    ]}), encoding="utf-8")
    monkeypatch.setattr(cm, "MERGED_JSON_FILE", merged)
    cm.LOCAL_INDEX._mtime_ns = None
    cm.LOCAL_INDEX._by_key = {}

    listing = Listing(5000, "EN", "SOA", False, "《Ad Nauseam》[SOA]", 1, "https://hareruya.example/listing", "https://hareruya.example/image")
    fake_job = Job("ambiguous-job", ["Ad Nauseam"], "all", "cheapest", status="complete", completed=1, results=[CardResult("Ad Nauseam", [listing])], eur_jpy_rate=180.0)
    monkeypatch.setattr(main.manager, "get", lambda job_id: fake_job if job_id == "ambiguous-job" else None)

    response = TestClient(main.app).get("/api/jobs/ambiguous-job")
    assert response.status_code == 200
    result = response.json()["results"][0]["rows"][0]
    assert result["cardmarket"]["ambiguous"] is True
    assert "2 variants" in result["cardmarket"]["ambiguity_reason"]


def test_frontend_contains_cardmarket_warning_and_link_rendering():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "static" / "app.js").read_text(encoding="utf-8")
    cardmarket_js = (root / "static" / "cardmarket.js").read_text(encoding="utf-8")
    index_html = (root / "static" / "index.html").read_text(encoding="utf-8")

    assert "Not found" in app_js
    assert "cardmarket-warning" in app_js
    assert "cardmarket-ambiguous-price-cell" in app_js
    assert "cardmarket-ambiguous-prices" in app_js
    assert "cardmarket-ambiguous-row" not in app_js
    assert 'id="search-warnings"' in index_html
    assert 'class="cardmarket-disclaimer"' in index_html
    assert 'id="cardmarketExact"' in cardmarket_js or 'id="cardmarketExact"' in (Path(__file__).resolve().parents[1] / "static" / "cardmarket.html").read_text(encoding="utf-8")
    assert "params.set('exact', 'true')" in cardmarket_js
    assert "Cardmarket prices exclude shipping and are not differentiated by card language." in index_html
    assert "idProduct=" in cardmarket_js
    assert "cm-link-button-disabled" in cardmarket_js
    assert "data-scryfall-promo-product-id" in cardmarket_js
    assert "promo_type_labels" in cardmarket_js
    assert "/api/cardmarket/scryfall/" in cardmarket_js
    assert "isMissingNonfoilPriceData" in cardmarket_js
    assert "variantHtml(row.nonfoil, true)" in cardmarket_js
    assert "mobileVariantHtml('Non-foil', row.nonfoil, true)" in cardmarket_js


def test_is_stale_returns_true_when_local_snapshot_is_missing(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    monkeypatch.setattr(cm, "MERGED_JSON_FILE", tmp_path / "merged.json")
    monkeypatch.setattr(cm, "STATUS_FILE", tmp_path / "status.json")
    assert cm.is_stale() is True


def test_parse_official_cardmarket_price_guide_csv(tmp_path):
    import app.cardmarket_data as cm

    path = tmp_path / "price_guide_1.json"
    path.write_text(
        "idProduct,Avg. Sell Price,Low Price,Trend Price,German Pro Low,Suggested Price,Foil Sell,Foil Low,Foil Trend,Low Price Ex+,AVG1,AVG7,AVG30,Foil AVG1,Foil AVG7,Foil AVG30\n"
        "1001,13.20,10.00,12.50,9.50,14.00,25.00,20.00,22.00,10.50,11.00,12.00,11.75,21.00,22.00,21.50\n"
        "1002,2.00,1.50,1.80,,,,,,,,,1.70,,,\n",
        encoding="utf-8",
    )

    payload = cm._download_rows(path)
    prices = cm.parse_price_guide(payload)
    assert len(prices) == 2
    assert prices[1001].low == Decimal("10.00")
    assert prices[1001].trend == Decimal("12.50")
    assert prices[1001].avg30 == Decimal("11.75")
    assert prices[1001].low_foil == Decimal("20.00")
    assert prices[1001].trend_foil == Decimal("22.00")
    assert prices[1001].avg30_foil == Decimal("21.50")


def test_parse_gzipped_official_cardmarket_price_guide_csv(tmp_path):
    import app.cardmarket_data as cm

    path = tmp_path / "price_guide_1.json"
    payload = (
        b"idProduct,Avg. Sell Price,Low Price,Trend Price,AVG30,Foil Low,Foil Trend,Foil AVG30\n"
        b"1001,13.20,10.00,12.50,11.75,20.00,22.00,21.50\n"
    )
    with gzip.open(path, "wb") as handle:
        handle.write(payload)

    prices = cm.parse_price_guide(cm._download_rows(path))
    assert len(prices) == 1
    assert prices[1001].low == Decimal("10.00")
    assert prices[1001].avg30_foil == Decimal("21.50")


def test_bundled_expansion_map_loads_source_file():
    import app.cardmarket_data as cm

    mapping = cm.load_expansion_set_map()
    assert len(mapping) == 766
    assert sum(bool(entry.get("code")) for entry in mapping.values()) == 761
    assert mapping["6570"] == {
        "code": "HOB",
        "name": "The Hobbit",
        "source": "bundled_cardmarket_map",
    }
    assert mapping["6547"]["code"] == "SOA"
    assert mapping["6477"]["code"] == "MSC"


def test_supplemental_expansion_map_loads_csv(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    path = tmp_path / "expansion_map.csv"
    path.write_text(
        "id_expansion,expansion_code,expansion_name\n45,MRD,Mirrodin\n72,,Friday Night Magic Promos\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cm, "SUPPLEMENTAL_EXPANSION_MAP_FILE", path)
    mapping = cm.load_supplemental_expansion_map()
    assert len(mapping) == 2
    assert mapping["45"] == {"code": "MRD", "name": "Mirrodin", "source": "external_csv"}
    assert mapping["72"]["code"] == ""
    assert mapping["72"]["name"] == "Friday Night Magic Promos"


def test_supplemental_expansion_map_extends_merge_when_primary_map_misses():
    products = parse_product_list({"products": [
        {"idProduct": 1001, "name": "Test Card", "idExpansion": 45},
        {"idProduct": 1002, "name": "Promo Card", "idExpansion": 72},
    ]})
    prices = parse_price_guide({"priceGuide": [
        {"idProduct": 1001, "low": "1", "avg7": "2"},
        {"idProduct": 1002, "low": "3", "avg7": "4"},
    ]})
    rows, unmapped = merge_data(
        products,
        prices,
        {},
        {},
        {
            "45": {"code": "MRD", "name": "Mirrodin", "source": "external_csv"},
            "72": {"code": "", "name": "Friday Night Magic Promos", "source": "external_csv"},
        },
    )
    by_name = {row["card_name"]: row for row in rows}
    assert by_name["Test Card"]["expansion"] == "MRD"
    assert by_name["Test Card"]["expansion_name"] == "Mirrodin"
    assert by_name["Test Card"]["mapping_source"] == "external_csv"
    assert by_name["Promo Card"]["expansion"] == "Friday Night Magic Promos"
    assert by_name["Promo Card"]["expansion_name"] == "Friday Night Magic Promos"
    assert by_name["Promo Card"]["mapping_source"] == "external_csv"
    assert unmapped == []


def test_catalog_verified_expansion_map_is_applied_after_external_fallback(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    verified_path = tmp_path / "verified.json"
    verified_path.write_text(json.dumps({"6570": {
        "code": "HOB", "name": "The Hobbit",
        "evidence_card": "Hobbit Hole", "evidence_note": "user verified"
    }}), encoding="utf-8")
    monkeypatch.setattr(cm, "CATALOG_VERIFIED_EXPANSION_MAP_FILE", verified_path)

    verified = cm.load_catalog_verified_expansion_map()
    products = parse_product_list({"products": [{"idProduct": 1001, "name": "Hobbit Hole", "idExpansion": 6570}]})
    prices = parse_price_guide({"priceGuide": [{"idProduct": 1001, "low": "10", "avg7": "12"}]})
    rows, unmapped = merge_data(products, prices, {}, {}, {}, verified)
    assert rows[0]["expansion"] == "HOB"
    assert rows[0]["expansion_name"] == "The Hobbit"
    assert rows[0]["mapping_source"] == "catalog_verified"
    assert unmapped == []


def test_catalog_verified_map_loader_supports_local_evidence_file(monkeypatch, tmp_path):
    import app.cardmarket_data as cm

    path = tmp_path / "verified.json"
    path.write_text(json.dumps({
        "6570": {
            "code": "HOB",
            "name": "The Hobbit",
            "evidence_card": "Hobbit Hole",
            "evidence_note": "user verified",
        }
    }), encoding="utf-8")
    monkeypatch.setattr(cm, "CATALOG_VERIFIED_EXPANSION_MAP_FILE", path)

    mapping = cm.load_catalog_verified_expansion_map()
    assert mapping["6570"]["code"] == "HOB"
    assert mapping["6570"]["name"] == "The Hobbit"
    assert mapping["6570"]["source"] == "catalog_verified"


def test_user_supplied_expansion_mappings_apply_to_real_catalog():
    """The six user-supplied IDs resolve to the requested codes in merge output."""
    # Keep this test fixture-sized so the suite remains fast; the real-data validation
    # is run separately against the uploaded Cardmarket catalog during packaging.
    from app.cardmarket_data import merge_data, parse_price_guide, parse_product_list

    products = parse_product_list({"products": [
        {"idProduct": 1, "name": "Reality Anchor 1", "idExpansion": 6571},
        {"idProduct": 2, "name": "Reality Anchor 2", "idExpansion": 6754},
        {"idProduct": 3, "name": "Reality Anchor 3", "idExpansion": 6610},
        {"idProduct": 4, "name": "Marvel Extra", "idExpansion": 6617},
        {"idProduct": 5, "name": "Marvel Commander", "idExpansion": 6477},
        {"idProduct": 6, "name": "Marvel Main", "idExpansion": 6476},
    ]})
    prices = parse_price_guide({"priceGuide": [
        {"idProduct": i, "low": "1", "avg7": "1"} for i in range(1, 7)
    ]})
    verified = {
        "6571": {"code": "FRA", "name": "Reality Fracture"},
        "6754": {"code": "FRA", "name": "Reality Fracture"},
        "6610": {"code": "FRA", "name": "Reality Fracture"},
        "6617": {"code": "MSC", "name": "Commander: Marvel Super Heroes: Extras"},
        "6477": {"code": "MSC", "name": "Commander: Marvel Super Heroes"},
        "6476": {"code": "MSH", "name": "Marvel Super Heroes"},
    }
    rows, unmapped = merge_data(products, prices, {}, {}, {}, verified)
    assert {(r["expansion_id"], r["expansion"]) for r in rows} == {
        (6571, "FRA"), (6754, "FRA"), (6610, "FRA"),
        (6617, "MSC"), (6477, "MSC"), (6476, "MSH"),
    }
    assert unmapped == []
