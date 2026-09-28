from app import scryfall


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

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


def test_cardmarket_image_uses_custom_scryfall_headers(monkeypatch):
    reset_cache()
    FakeClient.response = FakeResponse(
        payload={"image_uris": {"normal": "https://cards.scryfall.io/normal/example.jpg"}}
    )
    monkeypatch.setattr(scryfall.httpx, "Client", FakeClient)

    image = scryfall.get_cardmarket_image_url(19831)

    assert image == "https://cards.scryfall.io/normal/example.jpg"
    assert FakeClient.last_url == "https://api.scryfall.com/cards/cardmarket/19831"
    assert FakeClient.last_headers["User-Agent"] == scryfall.SCRYFALL_USER_AGENT
    assert FakeClient.last_headers["Accept"] == scryfall.SCRYFALL_ACCEPT


def test_cardmarket_image_result_is_cached(monkeypatch):
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

    assert scryfall.get_cardmarket_image_url(19831)
    assert scryfall.get_cardmarket_image_url(19831)
    assert calls == ["https://api.scryfall.com/cards/cardmarket/19831"]
