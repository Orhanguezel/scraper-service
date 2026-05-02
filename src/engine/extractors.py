import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from scrapling.parser import Selector

AI_CRAWLERS = [
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "ClaudeBot",
    "anthropic-ai",
    "PerplexityBot",
    "CCBot",
    "Bytespider",
    "cohere-ai",
    "Google-Extended",
    "GoogleOther",
    "Applebot-Extended",
    "FacebookBot",
    "Amazonbot",
]

SECURITY_HEADERS = [
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
]


def _text(value: Any) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _attrs(node: Any) -> dict[str, Any]:
    try:
        return dict(node.attrib)
    except Exception:
        return {}


def _css_texts(sel: Selector, selector: str) -> list[str]:
    return [str(item).strip() for item in sel.css(selector).getall() if str(item).strip()]


def _first(sel: Selector, selector: str) -> str | None:
    return _text(sel.css(selector).get(default=None))


def _header_value(headers: dict[str, Any], name: str) -> Any:
    if name in headers:
        return headers[name]
    lower_name = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lower_name:
            return value
    return None


def extract_basic_page_data(page: Any) -> dict[str, Any]:
    title = page.css("title::text").get(default=None)
    description = page.css('meta[name="description"]::attr(content)').get(default=None)
    canonical = page.css('link[rel="canonical"]::attr(href)').get(default=None)
    h1_tags = page.css("h1::text").getall()
    structured_data: list[Any] = []
    for raw in page.css('script[type="application/ld+json"]::text').getall():
        try:
            structured_data.append(json.loads(str(raw).strip()))
        except json.JSONDecodeError:
            continue
    return {
        "title": str(title) if title is not None else None,
        "description": str(description) if description is not None else None,
        "canonical": str(canonical) if canonical is not None else None,
        "h1_tags": [str(item) for item in h1_tags],
        "structured_data": structured_data,
    }


def extract_geo_page(html: str, url: str, response: Any) -> dict[str, Any]:
    sel = Selector(html, url=url)
    final_url = getattr(response, "url", url) or url
    headers = dict(getattr(response, "headers", {}) or {})
    parsed_url = urlparse(final_url)
    base_domain = parsed_url.netloc
    errors: list[str] = []

    meta_tags: dict[str, str] = {}
    for meta in sel.css("meta"):
        attrs = _attrs(meta)
        name = attrs.get("name") or attrs.get("property") or ""
        content = attrs.get("content") or ""
        if name and content:
            meta_tags[str(name).lower()] = str(content)

    structured_data: list[Any] = []
    for raw in sel.css('script[type="application/ld+json"]::text').getall():
        try:
            structured_data.append(json.loads(str(raw).strip()))
        except (json.JSONDecodeError, TypeError):
            errors.append("Invalid JSON-LD detected")

    heading_structure: list[dict[str, Any]] = []
    h1_tags: list[str] = []
    for level in range(1, 7):
        for text in _css_texts(sel, f"h{level}::text"):
            heading_structure.append({"level": level, "text": text})
            if level == 1:
                h1_tags.append(text)

    raw_html = html or ""
    visible_text = str(sel.get_all_text(separator=" ", strip=True, ignore_tags=("script", "style")))
    text_content = str(
        sel.get_all_text(
            separator=" ",
            strip=True,
            ignore_tags=("script", "style", "nav", "footer", "header"),
        )
    )
    word_count = len(text_content.split())

    og_tags: dict[str, str] = {}
    for meta in sel.css('meta[property^="og:"]'):
        attrs = _attrs(meta)
        if attrs.get("property") and attrs.get("content"):
            og_tags[str(attrs["property"])] = str(attrs["content"])

    twitter_tags: dict[str, str] = {}
    for meta in sel.css('meta[name^="twitter:"]'):
        attrs = _attrs(meta)
        if attrs.get("name") and attrs.get("content"):
            twitter_tags[str(attrs["name"])] = str(attrs["content"])

    hreflang_tags: list[dict[str, str]] = []
    for link in sel.css('link[rel="alternate"]'):
        attrs = _attrs(link)
        if attrs.get("hreflang"):
            hreflang_tags.append({"lang": str(attrs.get("hreflang", "")), "href": str(attrs.get("href", ""))})

    social_profiles: list[dict[str, str]] = []
    social_domains = {
        "facebook": r"(?:facebook\.com|fb\.com)/(?!sharer|share)",
        "twitter": r"(?:twitter\.com|x\.com)/(?!intent|share)",
        "instagram": r"instagram\.com/",
        "linkedin": r"linkedin\.com/(?:company|in)/",
        "youtube": r"youtube\.com/(?:channel|c|@|user)/",
        "tiktok": r"tiktok\.com/@",
        "pinterest": r"pinterest\.com/",
        "github": r"github\.com/(?!login|signup)",
    }
    seen_social: set[str] = set()

    internal_links: list[dict[str, str]] = []
    external_links: list[dict[str, str]] = []
    for link in sel.css("a[href]"):
        attrs = _attrs(link)
        href_raw = str(attrs.get("href", ""))
        href = urljoin(final_url, href_raw)
        link_text = str(link.get_all_text(separator=" ", strip=True))
        parsed_href = urlparse(href)
        if parsed_href.netloc == base_domain:
            internal_links.append({"url": href, "text": link_text})
        elif parsed_href.scheme in ("http", "https"):
            external_links.append({"url": href, "text": link_text})
        for platform, pattern in social_domains.items():
            if platform not in seen_social and re.search(pattern, href, re.I):
                social_profiles.append({"platform": platform, "url": href})
                seen_social.add(platform)

    images: list[dict[str, Any]] = []
    for img in sel.css("img"):
        attrs = _attrs(img)
        images.append(
            {
                "src": str(attrs.get("src", "")),
                "alt": str(attrs.get("alt", "")),
                "width": attrs.get("width"),
                "height": attrs.get("height"),
                "loading": attrs.get("loading"),
            }
        )

    js_files = [str(src) for src in sel.css("script[src]::attr(src)").getall()]
    css_files = [str(href) for href in sel.css('link[rel="stylesheet"]::attr(href)').getall() if str(href)]
    inline_scripts = [str(script) for script in sel.css("script:not([src])::text").getall()]
    inline_styles = [str(style) for style in sel.css("style::text").getall()]

    minification_status: dict[str, bool | None] = {"js_minified": None, "css_minified": None}
    if inline_scripts:
        total_len = sum(len(item) for item in inline_scripts)
        total_lines = sum(item.count("\n") + 1 for item in inline_scripts)
        if total_lines > 0 and total_len > 100:
            minification_status["js_minified"] = (total_len / total_lines) > 200
    if js_files and minification_status["js_minified"] is None:
        minification_status["js_minified"] = sum(1 for item in js_files if ".min." in item) > len(js_files) * 0.5
    if inline_styles:
        total_len = sum(len(item) for item in inline_styles)
        total_lines = sum(item.count("\n") + 1 for item in inline_styles)
        if total_lines > 0 and total_len > 100:
            minification_status["css_minified"] = (total_len / total_lines) > 200
    if css_files and minification_status["css_minified"] is None:
        minification_status["css_minified"] = sum(1 for item in css_files if ".min." in item) > len(css_files) * 0.5

    deprecated_tags = []
    for tag_name in ["font", "center", "marquee", "blink", "big", "strike", "tt", "frame", "frameset", "applet", "basefont", "dir", "isindex", "menu", "s", "u"]:
        count = len(sel.css(tag_name))
        if count:
            deprecated_tags.append({"tag": tag_name, "count": count})

    has_flash = False
    for node in list(sel.css("object")) + list(sel.css("embed")):
        attrs = _attrs(node)
        node_type = str(attrs.get("type", "")).lower()
        src = str(attrs.get("src", ""))
        if "application/x-shockwave-flash" in node_type or "application/x-java-applet" in node_type or src.endswith(".swf"):
            has_flash = True
            break

    iframes = [
        {"src": str(_attrs(iframe).get("src", "")), "title": str(_attrs(iframe).get("title", ""))}
        for iframe in sel.css("iframe")
    ]
    plaintext_emails = sorted(set(re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", visible_text)))

    html_tag = sel.css("html").get(default=None)
    html_attrs = _attrs(sel.css("html").first) if sel.css("html").first else {}
    has_amp = "amp" in html_attrs or "⚡" in html_attrs
    has_amp_link = _first(sel, 'link[rel="amphtml"]::attr(href)')
    if has_amp_link:
        has_amp = True

    favicon_rels = {"icon", "shortcut icon", "apple-touch-icon"}
    has_favicon = False
    for link in sel.css("link[rel]"):
        rel = _attrs(link).get("rel", "")
        rel_text = " ".join(rel) if isinstance(rel, list) else str(rel)
        if any(item in rel_text for item in favicon_rels):
            has_favicon = True
            break

    analytics_patterns = {
        "Google Analytics (gtag.js)": r"gtag\s*\(",
        "Google Analytics (analytics.js)": r"google-analytics\.com/analytics\.js",
        "Google Analytics 4": r"googletagmanager\.com/gtag",
        "Google Tag Manager": r"googletagmanager\.com/gtm\.js",
        "Facebook Pixel": r"fbq\s*\(|connect\.facebook\.net/",
        "Hotjar": r"hotjar\.com",
        "Microsoft Clarity": r"clarity\.ms",
        "Yandex Metrica": r"mc\.yandex\.ru|yandex\.ru/metrika",
        "Matomo/Piwik": r"matomo|piwik",
        "Plausible": r"plausible\.io",
        "Fathom": r"usefathom\.com",
    }
    analytics_tools = [name for name, pattern in analytics_patterns.items() if re.search(pattern, raw_html, re.I)]

    root_checks = []
    for root in sel.css("#app, #root, #__next, #__nuxt"):
        attrs = _attrs(root)
        root_checks.append({"id": attrs.get("id", "unknown"), "text_length": len(str(root.get_all_text(strip=True)))})
    has_ssr_content = True
    for check in root_checks:
        if check["text_length"] < 50 and word_count < 200:
            has_ssr_content = False
            errors.append(
                f"Possible client-side only rendering detected: #{check['id']} has minimal server-rendered content ({word_count} words on page)"
            )

    html_size_bytes = len(raw_html.encode("utf-8"))
    return {
        "url": url,
        "final_url": final_url,
        "is_https": final_url.lower().startswith("https://"),
        "status_code": getattr(response, "status", None),
        "redirect_chain": [
            {"url": getattr(item, "url", ""), "status": getattr(item, "status", None)}
            for item in (getattr(response, "history", None) or [])
        ],
        "headers": headers,
        "meta_tags": meta_tags,
        "title": _first(sel, "title::text"),
        "description": meta_tags.get("description"),
        "canonical": _first(sel, 'link[rel="canonical"]::attr(href)'),
        "h1_tags": h1_tags,
        "heading_structure": heading_structure,
        "word_count": word_count,
        "text_content": text_content,
        "internal_links": internal_links,
        "external_links": external_links,
        "images": images,
        "structured_data": structured_data,
        "has_ssr_content": has_ssr_content,
        "security_headers": {header: _header_value(headers, header) for header in SECURITY_HEADERS},
        "analytics_tools": analytics_tools,
        "social_profiles": social_profiles,
        "has_favicon": has_favicon,
        "inline_styles_count": len(sel.css("[style]")),
        "deprecated_tags": deprecated_tags,
        "has_flash": has_flash,
        "iframes": iframes,
        "plaintext_emails": plaintext_emails,
        "is_http2": None,
        "has_amp": has_amp,
        "has_amp_link": has_amp_link,
        "resource_breakdown": {"js": len(js_files), "css": len(css_files), "img": len(images), "other": 0},
        "js_files": js_files,
        "css_files": css_files,
        "minification_status": minification_status,
        "has_hreflang": bool(hreflang_tags),
        "hreflang_tags": hreflang_tags,
        "lang_attribute": html_attrs.get("lang"),
        "og_tags": og_tags,
        "twitter_tags": twitter_tags,
        "text_to_html_ratio": round((len(text_content) / (len(raw_html) or 1)) * 100, 1),
        "html_size_bytes": html_size_bytes,
        "errors": errors,
    }


def extract_geo_robots(robots_text: str, robots_url: str, status_code: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": robots_url,
        "exists": status_code == 200,
        "content": robots_text if status_code == 200 else "",
        "ai_crawler_status": {},
        "sitemaps": [],
        "errors": [],
    }

    if status_code == 404:
        result["errors"].append("No robots.txt found (404)")
        for crawler in AI_CRAWLERS:
            result["ai_crawler_status"][crawler] = "NO_ROBOTS_TXT"
        return result
    if status_code != 200:
        result["errors"].append(f"Unexpected status code: {status_code}")
        return result

    current_agent: str | None = None
    agent_rules: dict[str, list[dict[str, str]]] = {}
    for line in robots_text.split("\n"):
        line = line.strip()
        if line.lower().startswith("user-agent:"):
            current_agent = line.split(":", 1)[1].strip()
            agent_rules.setdefault(current_agent, [])
        elif line.lower().startswith("disallow:") and current_agent:
            agent_rules[current_agent].append({"directive": "Disallow", "path": line.split(":", 1)[1].strip()})
        elif line.lower().startswith("allow:") and current_agent:
            agent_rules[current_agent].append({"directive": "Allow", "path": line.split(":", 1)[1].strip()})
        elif line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if not sitemap_url.startswith("http"):
                sitemap_url = "http" + sitemap_url
            result["sitemaps"].append(sitemap_url)

    for crawler in AI_CRAWLERS:
        if crawler in agent_rules:
            rules = agent_rules[crawler]
            if any(rule["directive"] == "Disallow" and rule["path"] == "/" for rule in rules):
                result["ai_crawler_status"][crawler] = "BLOCKED"
            elif any(rule["directive"] == "Disallow" and rule["path"] for rule in rules):
                result["ai_crawler_status"][crawler] = "PARTIALLY_BLOCKED"
            else:
                result["ai_crawler_status"][crawler] = "ALLOWED"
        elif "*" in agent_rules:
            wildcard_rules = agent_rules["*"]
            if any(rule["directive"] == "Disallow" and rule["path"] == "/" for rule in wildcard_rules):
                result["ai_crawler_status"][crawler] = "BLOCKED_BY_WILDCARD"
            else:
                result["ai_crawler_status"][crawler] = "ALLOWED_BY_DEFAULT"
        else:
            result["ai_crawler_status"][crawler] = "NOT_MENTIONED"

    return result
