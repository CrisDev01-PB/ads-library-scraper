"""Async parallel video download — replaces the sequential curl loop."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class DownloadResult:
    index: int
    path: Path
    bytes: int
    ok: bool
    error: str = ""


async def _download_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    index: int,
    url: str,
    out_path: Path,
) -> DownloadResult:
    if not url:
        return DownloadResult(index, out_path, 0, False, "no url")
    async with sem:
        try:
            async with client.stream("GET", url, timeout=60.0) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=64 * 1024):
                        f.write(chunk)
            size = out_path.stat().st_size
            if size < 1000:
                return DownloadResult(index, out_path, size, False, "too small")
            return DownloadResult(index, out_path, size, True)
        except Exception as e:
            return DownloadResult(index, out_path, 0, False, str(e))


async def _run(jobs, concurrency: int, on_done) -> list[DownloadResult]:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            _download_one(client, sem, idx, url, out)
            for idx, url, out in jobs
        ]
        results: list[DownloadResult] = []
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if on_done:
                on_done(res)
            results.append(res)
        return sorted(results, key=lambda r: r.index)


def download_videos(
    jobs: list[tuple[int, str, Path]],
    concurrency: int = 8,
    on_done=None,
) -> list[DownloadResult]:
    """Download a list of (index, url, out_path) jobs in parallel."""
    return asyncio.run(_run(jobs, concurrency, on_done))
