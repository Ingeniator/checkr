import asyncio
from typing import Any, Coroutine


async def gather_with_semaphore(
    coros: list[Coroutine],
    max_concurrency: int = 10,
    return_exceptions: bool = True,
) -> list[Any]:
    """Run coroutines concurrently with a concurrency limit, preserving input order."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _wrap(coro: Coroutine) -> Any:
        async with semaphore:
            return await coro

    return await asyncio.gather(
        *(_wrap(c) for c in coros),
        return_exceptions=return_exceptions,
    )
