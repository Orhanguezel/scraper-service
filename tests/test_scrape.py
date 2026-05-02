from src.engine.selectors import extract_selectors
from src.lib.cache import build_cache_key
from src.schemas.scrape import ScrapeRequest


class FakeSelection:
    def __init__(self, values):
        self.values = values

    def getall(self):
        return self.values


class FakePage:
    def css(self, selector):
        if selector == "title::text":
            return FakeSelection(["Example"])
        return FakeSelection([])


def test_cache_key_ignores_return_flags():
    one = ScrapeRequest(url="https://example.com", return_html=True)
    two = ScrapeRequest(url="https://example.com", return_text=True)

    assert build_cache_key(one) == build_cache_key(two)


def test_extract_selectors_single_value_is_scalar():
    data = extract_selectors(FakePage(), {"title": "title::text"})

    assert data["title"] == "Example"
