"""Tests for the rate limiter."""

from zeus.security.rate_limit import RateLimiter


def test_rate_limiter_allows_under_limit():
    limiter = RateLimiter(max_per_minute=3, max_per_hour=10)
    assert limiter.is_allowed("test")
    assert limiter.is_allowed("test")
    assert limiter.is_allowed("test")


def test_rate_limiter_blocks_over_limit():
    limiter = RateLimiter(max_per_minute=2, max_per_hour=10)
    assert limiter.is_allowed("test")
    assert limiter.is_allowed("test")
    assert not limiter.is_allowed("test")


def test_rate_limiter_tracks_actions_separately():
    limiter = RateLimiter(max_per_minute=1, max_per_hour=10)
    assert limiter.is_allowed("a")
    assert not limiter.is_allowed("a")
    assert limiter.is_allowed("b")


def test_rate_limiter_per_user_quota():
    limiter = RateLimiter(
        max_per_minute=10,
        max_per_hour=100,
        max_per_minute_per_user=1,
        max_per_hour_per_user=10,
    )
    assert limiter.is_allowed("test", user_id="alice")
    assert not limiter.is_allowed("test", user_id="alice")
    assert limiter.is_allowed("test", user_id="bob")


def test_rate_limiter_reset():
    limiter = RateLimiter(max_per_minute=1, max_per_hour=10)
    assert limiter.is_allowed("test")
    assert not limiter.is_allowed("test")
    limiter.reset("test")
    assert limiter.is_allowed("test")
