import asyncio
import time
import pytest
from utils.async_utils import gather_with_semaphore


@pytest.mark.asyncio
async def test_preserves_input_order():
    """Results are returned in the same order as the input coroutines."""
    async def identity(x):
        await asyncio.sleep(0.01 * (10 - x))  # reverse delay so faster items finish first
        return x

    coros = [identity(i) for i in range(10)]
    results = await gather_with_semaphore(coros, max_concurrency=5)
    assert results == list(range(10))


@pytest.mark.asyncio
async def test_concurrency_limit():
    """No more than max_concurrency coroutines run at the same time."""
    peak = 0
    current = 0
    lock = asyncio.Lock()

    async def track():
        nonlocal peak, current
        async with lock:
            current += 1
            if current > peak:
                peak = current
        await asyncio.sleep(0.05)
        async with lock:
            current -= 1

    coros = [track() for _ in range(20)]
    await gather_with_semaphore(coros, max_concurrency=3)
    assert peak <= 3


@pytest.mark.asyncio
async def test_return_exceptions_true():
    """With return_exceptions=True (default), exceptions are returned, not raised."""
    async def fail():
        raise ValueError("boom")

    async def succeed():
        return 42

    results = await gather_with_semaphore([succeed(), fail(), succeed()])
    assert results[0] == 42
    assert isinstance(results[1], ValueError)
    assert results[2] == 42


@pytest.mark.asyncio
async def test_return_exceptions_false():
    """With return_exceptions=False, first exception propagates."""
    async def fail():
        raise ValueError("boom")

    async def succeed():
        return 42

    with pytest.raises(ValueError, match="boom"):
        await gather_with_semaphore([succeed(), fail()], return_exceptions=False)


@pytest.mark.asyncio
async def test_empty_input():
    """Empty coroutine list returns empty results."""
    results = await gather_with_semaphore([])
    assert results == []


@pytest.mark.asyncio
async def test_actual_speedup():
    """Concurrent execution is faster than sequential."""
    async def slow():
        await asyncio.sleep(0.1)
        return True

    start = time.monotonic()
    results = await gather_with_semaphore([slow() for _ in range(10)], max_concurrency=10)
    elapsed = time.monotonic() - start

    assert all(results)
    # 10 tasks * 0.1s sequentially = 1s; concurrently should be ~0.1s
    assert elapsed < 0.5
