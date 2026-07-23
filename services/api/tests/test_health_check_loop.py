"""Health-check loop unit tests."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


class TestStartStop:
    @pytest.mark.anyio
    async def test_start_and_stop(self):
        from app.services import health_check_loop as hcl
        from app.services.health_check_loop import (
            start_health_check,
            stop_health_check,
        )

        async def fake_loop(_interval_s: int) -> None:
            await asyncio.Event().wait()

        with patch.object(hcl, "health_check_loop", fake_loop):
            start_health_check(60)
            assert hcl._health_check_task is not None
            stop_health_check()
            await asyncio.sleep(0.05)

    @pytest.mark.anyio
    async def test_double_start_is_noop(self):
        from app.services import health_check_loop as hcl
        from app.services.health_check_loop import (
            start_health_check,
            stop_health_check,
        )

        async def fake_loop(_interval_s: int) -> None:
            await asyncio.Event().wait()

        with patch.object(hcl, "health_check_loop", fake_loop):
            start_health_check(60)
            t1 = hcl._health_check_task
            start_health_check(60)
            assert hcl._health_check_task is t1
            stop_health_check()
            await asyncio.sleep(0.05)
