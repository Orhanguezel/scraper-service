from typing import Any


def extract_selectors(page: Any, selectors: dict[str, str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, selector in selectors.items():
        selector = selector.strip()
        if not selector:
            data[key] = None
            continue

        try:
            if selector.startswith("xpath:"):
                values = page.xpath(selector.removeprefix("xpath:")).getall()
            else:
                values = page.css(selector).getall()
            data[key] = values[0] if len(values) == 1 else values
        except Exception as exc:  # Selector failures should not fail the full scrape.
            data[key] = {"error": str(exc)}
    return data
