from app import scryfall


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise scryfall.httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=scryfall.httpx.Request("GET", "https://api.scryfall.com"),
                response=scryfall.httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


class FakeClient:
    last_headers = None
    last_url = None
    response = None

    def __init__(self, headers, follow_redirects, timeout):
        type(self).last_headers = headers
        type(self).follow_redirects = follow_redirects
        type(self).timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        type(self).last_url = url
        return type(self).response


def reset_cache():
    scryfall._cache.clear()
    scryfall._last_request_at = 0.0


def test_cardmarket_lookup_uses_custom_headers_and_returns_promo_labels(monkeypatch):
    reset_cache()
    FakeClient.response = FakeResponse(
        payload={
            "image_uris": {"normal": "https://cards.scryfall.io/normal/example.jpg"},
            "promo_types": ["surgefoil", "universesbeyond", "fracturefoil", "foiletched", "serialized"],
        }
    )
    monkeypatch.setattr(scryfall.httpx, "Client", FakeClient)

    info = scryfall.get_cardmarket_card_info(900736)

    assert info is not None
    assert info.image_url == "https://cards.scryfall.io/normal/example.jpg"
    assert info.promo_types == ("surgefoil", "universesbeyond", "fracturefoil", "foiletched", "serialized")
    assert info.promo_type_labels == ("Surge Foil", "Fracture Foil", "Foil Etched", "Serialized")
    assert FakeClient.last_url == "https://api.scryfall.com/cards/cardmarket/900736"
    assert FakeClient.last_headers["User-Agent"] == scryfall.SCRYFALL_USER_AGENT
    assert FakeClient.last_headers["Accept"] == scryfall.SCRYFALL_ACCEPT


def test_cardmarket_image_url_uses_cached_card_info(monkeypatch):
    reset_cache()
    FakeClient.response = FakeResponse(
        payload={"image_uris": {"normal": "https://cards.scryfall.io/normal/example.jpg"}}
    )
    calls = []

    class CountingClient(FakeClient):
        def get(self, url):
            calls.append(url)
            return super().get(url)

    monkeypatch.setattr(scryfall.httpx, "Client", CountingClient)

    assert scryfall.get_cardmarket_image_url(19831) == "https://cards.scryfall.io/normal/example.jpg"
    assert scryfall.get_cardmarket_image_url(19831) == "https://cards.scryfall.io/normal/example.jpg"
    assert calls == ["https://api.scryfall.com/cards/cardmarket/19831"]


def test_cardmarket_promo_label_parser_supports_foil_variants():
    labels = scryfall._promo_type_labels(["surgefoil", "fracturefoil", "etchedfoil", "foiletched", "doublerainbow", "serialized", "universesbeyond"])
    assert labels == ("Surge Foil", "Fracture Foil", "Etched Foil", "Foil Etched", "Double Rainbow Foil", "Serialized")
