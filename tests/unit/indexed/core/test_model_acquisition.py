"""Unit tests for the bounded, categorized model-acquisition seam."""

import pytest

from indexed.core import model_acquisition as ma
from indexed.core.errors import ModelAcquisitionError


class _StatusError(Exception):
    def __init__(self, status: int, headers: dict | None = None) -> None:
        self.response = type(
            "R", (), {"status_code": status, "headers": headers or {}}
        )()


class TestCategorize:
    def test_network_for_oserror(self):
        assert ma.categorize(ConnectionError("dns")) == ma.NETWORK
        assert ma.categorize(OSError("socket reset")) == ma.NETWORK

    def test_rate_limit_for_429(self):
        assert ma.categorize(_StatusError(429)) == ma.RATE_LIMIT

    def test_auth_for_401_403_and_gated(self):
        assert ma.categorize(_StatusError(401)) == ma.AUTH
        assert ma.categorize(_StatusError(403)) == ma.AUTH
        gated = type("GatedRepoError", (Exception,), {})("gated")
        assert ma.categorize(gated) == ma.AUTH

    def test_missing_for_404_and_repo_not_found(self):
        assert ma.categorize(_StatusError(404)) == ma.MISSING
        not_found = type("RepositoryNotFoundError", (Exception,), {})("nope")
        assert ma.categorize(not_found) == ma.MISSING

    def test_unknown_for_other(self):
        assert ma.categorize(ValueError("weird")) == ma.UNKNOWN

    def test_retryable_only_transient(self):
        assert ma.is_retryable(ma.NETWORK)
        assert ma.is_retryable(ma.RATE_LIMIT)
        assert not ma.is_retryable(ma.AUTH)
        assert not ma.is_retryable(ma.MISSING)
        assert not ma.is_retryable(ma.UNKNOWN)


class TestRedact:
    def test_strips_hf_token(self):
        # Built at runtime so the literal is not token-shaped in the source.
        fake_token = "hf_" + "A" * 24
        out = ma.redact(f"using token {fake_token}")
        assert fake_token not in out
        assert "hf_***" in out

    def test_strips_authorization_header(self):
        fake_token = "B" * 24
        out = ma.redact(f"Authorization: Bearer {fake_token}")
        assert fake_token not in out
        assert "***" in out

    def test_strips_url_credentials(self):
        fake = "user" + ":" + "pass"
        out = ma.redact(f"https://{fake}@huggingface.co/model")
        assert fake not in out


class TestAcquireWithRetry:
    def test_returns_on_success(self):
        result = ma.acquire_with_retry(
            lambda: 42,
            model_name="m",
            action="download",
            cache_dir="/c",
            cache_state=lambda: "not cached",
        )
        assert result == 42

    def test_retries_transient_then_succeeds(self):
        attempts: list[int] = []
        slept: list[float] = []

        def flaky() -> str:
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("blip")
            return "ok"

        result = ma.acquire_with_retry(
            flaky,
            model_name="m",
            action="download",
            cache_dir="/c",
            cache_state=lambda: "not cached",
            sleep=slept.append,
        )
        assert result == "ok"
        assert len(attempts) == 2
        assert slept == [ma.BASE_DELAY_SECONDS]

    def test_exhausts_budget_and_wraps(self):
        def boom() -> None:
            raise ConnectionError("down")

        with pytest.raises(ModelAcquisitionError) as excinfo:
            ma.acquire_with_retry(
                boom,
                model_name="m",
                action="download",
                cache_dir="/c",
                cache_state=lambda: "not cached",
                sleep=lambda seconds: None,
            )
        assert excinfo.value.attempts == ma.MAX_ATTEMPTS
        assert excinfo.value.category == ma.NETWORK

    def test_permanent_failure_not_retried(self):
        calls: list[int] = []

        def boom() -> None:
            calls.append(1)
            raise _StatusError(401)

        with pytest.raises(ModelAcquisitionError) as excinfo:
            ma.acquire_with_retry(
                boom,
                model_name="m",
                action="download",
                cache_dir="/c",
                cache_state=lambda: "not cached",
                sleep=lambda seconds: None,
            )
        assert len(calls) == 1
        assert excinfo.value.category == ma.AUTH

    def test_honors_retry_after(self):
        def boom() -> None:
            raise _StatusError(429, headers={"Retry-After": "5"})

        slept: list[float] = []
        with pytest.raises(ModelAcquisitionError):
            ma.acquire_with_retry(
                boom,
                model_name="m",
                action="download",
                cache_dir="/c",
                cache_state=lambda: "not cached",
                base_delay=1.0,
                sleep=slept.append,
            )
        assert slept == [5.0, 5.0]  # Retry-After overrides the shorter backoff


class TestModelAcquisitionError:
    def test_message_names_model_cache_and_remedy(self):
        err = ModelAcquisitionError(
            "all-MiniLM-L6-v2",
            action="download",
            category="network",
            cache_dir="/cache",
            cache_state="not cached",
            attempts=3,
        )
        message = str(err)
        assert "all-MiniLM-L6-v2" in message
        assert "/cache" in message
        assert "not cached" in message
        assert "3 attempts" in message
        assert "indexed init" in message
