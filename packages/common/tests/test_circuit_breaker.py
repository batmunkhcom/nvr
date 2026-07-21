"""Unit tests for CircuitBreaker — timed auto-reset, trip, reset behavior."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from nvr_common.circuit_breaker import CircuitBreaker


class TestCircuitBreakerBasic:
    def test_initial_state(self):
        cb = CircuitBreaker(name="test", base_cooldown=60, max_cooldown=600)
        assert cb.name == "test"
        assert cb.trip_count == 0
        assert cb.circuit_open_until == 0.0

    @pytest.mark.anyio
    async def test_not_open_initially(self):
        cb = CircuitBreaker(name="test")
        assert not await cb.is_open()


class TestCircuitBreakerTrip:
    def test_trip_sets_cooldown(self):
        cb = CircuitBreaker(name="test", base_cooldown=60, max_cooldown=600)
        cb.trip()
        assert cb.trip_count == 1
        assert cb.circuit_open_until > time.time()

    def test_trip_exponential_backoff(self):
        cb = CircuitBreaker(name="test", base_cooldown=60, max_cooldown=600)

        cb.trip()
        cooldown1 = cb.circuit_open_until - time.time()
        assert 55 <= cooldown1 <= 65, f"Expected ~60, got {cooldown1}"

        cb.trip()
        cooldown2 = cb.circuit_open_until - time.time()
        assert 115 <= cooldown2 <= 125, f"Expected ~120, got {cooldown2}"

        cb.trip()
        cooldown3 = cb.circuit_open_until - time.time()
        assert 235 <= cooldown3 <= 245, f"Expected ~240, got {cooldown3}"

    def test_trip_max_cooldown_cap(self):
        cb = CircuitBreaker(name="test", base_cooldown=60, max_cooldown=600)
        cb.trip_count = 10
        cb.trip()
        cooldown = cb.circuit_open_until - time.time()
        assert cooldown <= 600 + 5

    def test_trip_increments_count(self):
        cb = CircuitBreaker(name="test")
        for _ in range(5):
            cb.trip()
        assert cb.trip_count == 5


class TestCircuitBreakerAutoReset:
    @pytest.mark.anyio
    async def test_auto_reset_after_cooldown(self):
        cb = CircuitBreaker(name="test", base_cooldown=1, max_cooldown=600)
        cb.trip()

        future = time.time() + 2.0
        with patch("time.time", return_value=future):
            assert not await cb.is_open()

    @pytest.mark.anyio
    async def test_still_open_during_cooldown(self):
        cb = CircuitBreaker(name="test", base_cooldown=60)
        cb.trip()
        assert await cb.is_open() is True

    @pytest.mark.anyio
    async def test_auto_reset_clears_open_until(self):
        cb = CircuitBreaker(name="test", base_cooldown=1)
        cb.trip()

        future = time.time() + 2.0
        with patch("time.time", return_value=future):
            await cb.is_open()

        assert cb.circuit_open_until == 0.0


class TestCircuitBreakerReset:
    def test_reset_clears_state(self):
        cb = CircuitBreaker(name="test")
        cb.trip()
        cb.trip()

        cb.reset()

        assert cb.trip_count == 0
        assert cb.circuit_open_until == 0.0

    @pytest.mark.anyio
    async def test_reset_closes_circuit(self):
        cb = CircuitBreaker(name="test", base_cooldown=60)
        cb.trip()
        cb.reset()
        assert not await cb.is_open()

    def test_reset_then_trip_starts_fresh(self):
        cb = CircuitBreaker(name="test", base_cooldown=60)
        cb.trip()
        cb.trip()
        cb.reset()
        cb.trip()

        assert cb.trip_count == 1
        cooldown = cb.circuit_open_until - time.time()
        assert 55 <= cooldown <= 65


class TestCircuitBreakerCooldownRemaining:
    def test_returns_zero_when_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.cooldown_remaining() == 0

    def test_returns_positive_when_open(self):
        cb = CircuitBreaker(name="test", base_cooldown=60)
        cb.trip()
        remaining = cb.cooldown_remaining()
        assert 50 <= remaining <= 60

    def test_never_negative(self):
        cb = CircuitBreaker(name="test", base_cooldown=60)
        cb.trip()
        cb.circuit_open_until = time.time() - 1
        assert cb.cooldown_remaining() == 0


class TestCircuitBreakerEdgeCases:
    def test_multiple_resets_idempotent(self):
        cb = CircuitBreaker(name="test")
        for _ in range(3):
            cb.trip()
        cb.reset()
        cb.reset()
        assert cb.trip_count == 0

    @pytest.mark.anyio
    async def test_long_cooldown_auto_reset(self):
        cb = CircuitBreaker(name="test", base_cooldown=100, max_cooldown=600)
        cb.trip()
        cb.trip()

        future = time.time() + 300
        with patch("time.time", return_value=future):
            assert not await cb.is_open()
