from pathlib import Path

import pytest

from src.engine.places.google_maps import (
    _build_search_url,
    _parse_coordinates,
    parse_place_from_panel_html,
)
from src.schemas.places import GoogleMapsSearchRequest


@pytest.mark.parametrize(
    ("query", "language", "region", "expect_gl", "expect_hl"),
    [
        ("kahve konya", "tr", None, False, "hl=tr"),
        ("cafe", "en", "us", True, "hl=en"),
        ("x y", "de", None, False, "hl=de"),
        ("özel", "tr", "tr", True, "hl=tr"),
    ],
)
def test_build_search_url(query, language, region, expect_gl, expect_hl):
    url = _build_search_url(query, language, region)
    assert "https://www.google.com/maps/search/" in url
    assert expect_hl in url
    assert ("gl=" in url) is expect_gl


@pytest.mark.parametrize(
    ("place_url", "lat", "lng"),
    [
        ("https://www.google.com/maps/place/Foo/@37.123456,32.987654,15z", 37.123456, 32.987654),
        ("https://www.google.com/maps/@-33.8,151.2,12z", -33.8, 151.2),
        ("https://example.com/no-coords", None, None),
    ],
)
def test_parse_coordinates(place_url, lat, lng):
    c = _parse_coordinates(place_url)
    if lat is None:
        assert c is None
    else:
        assert c is not None
        assert abs(c.lat - lat) < 1e-9
        assert abs(c.lng - lng) < 1e-9


def test_parse_place_from_fixture_panel():
    html = Path(__file__).resolve().parents[1] / "fixtures" / "maps_place_panel.html"
    place = parse_place_from_panel_html(html.read_text(encoding="utf-8"))
    assert place is not None
    assert place.name == "Örnek Kafe Konya"
    assert place.address and "Konya" in place.address
    assert place.website == "https://example-cafe.com"
    assert place.phone and "332" in place.phone
    assert place.reviews_count == 128
    assert place.reviews_average is not None
    assert abs(place.reviews_average - 4.6) < 0.01
    assert place.place_type == "Kafe"


def test_google_maps_request_defaults():
    r = GoogleMapsSearchRequest(query="ab")
    assert r.total == 20
    assert r.language == "tr"
