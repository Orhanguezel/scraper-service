from src.engine.places.browser import CHROMIUM_ARGS, UA_POOL, VIEWPORTS, _accept_language_header


def test_ua_pool_has_eight_entries():
    assert len(UA_POOL) == 8


def test_chromium_args_include_automation_disable():
    joined = " ".join(CHROMIUM_ARGS)
    assert "AutomationControlled" in joined
    assert "--no-sandbox" in CHROMIUM_ARGS


def test_viewports_non_empty():
    assert len(VIEWPORTS) >= 3
    for w, h in VIEWPORTS:
        assert w > 0 and h > 0


def test_accept_language_tr_and_en():
    assert "tr-TR" in _accept_language_header("tr")
    assert "de-DE" in _accept_language_header("de")
