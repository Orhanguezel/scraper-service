from src.schemas.job import JobCreateRequest
from src.workers.webhook import sign_payload


def test_job_create_request_accepts_scrape_payload():
    request = JobCreateRequest(
        type="scrape",
        payload={"url": "https://example.com", "mode": "fast"},
    )

    assert request.type == "scrape"


def test_webhook_signature_is_sha256_prefixed():
    signature = sign_payload("secret-value", b'{"ok":true}')

    assert signature.startswith("sha256=")
    assert len(signature) == len("sha256=") + 64
