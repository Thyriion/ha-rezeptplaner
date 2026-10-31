"""Background import of HelloFresh recipes into the local catalog.

Politeness: one request every few seconds, identifiable User-Agent, only URLs
listed in the site's own recipe sitemap (which robots.txt permits). Data is kept
locally for private household use.
"""
import asyncio
import logging
import re
from collections.abc import Awaitable, Callable

import httpx

from .catalog import parse_recipe_page
from .database import PlanStore

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.hellofresh.de/sitemap_recipe_pages.xml"
USER_AGENT = "ha-rezeptplaner/1.0 (private household add-on; polite crawler)"
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
_MAX_CONSECUTIVE_ERRORS = 10

Fetch = Callable[[str], Awaitable[str]]


def _recency_key(url: str) -> int:
    """HelloFresh ids end in a Mongo ObjectId whose first 4 bytes are a timestamp."""
    try:
        return int(url.rstrip("/").rsplit("-", 1)[-1][:8], 16)
    except ValueError:
        return 0


class CatalogImporter:
    def __init__(self, store: PlanStore, fetch: Fetch | None = None, delay: float = 2.0) -> None:
        self._store = store
        self._fetch = fetch or self._http_fetch
        self._delay = delay
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self.status: dict = self._idle_status()

    @staticmethod
    def _idle_status(**overrides) -> dict:
        return {"running": False, "total": 0, "processed": 0, "imported": 0,
                "skipped": 0, "errors": 0, "last_error": None, **overrides}

    async def _http_fetch(self, url: str) -> str:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True
            )
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.text

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, limit: int | None = None) -> bool:
        """Start a background import. Returns False if one is already running."""
        if self.running:
            return False
        self.status = self._idle_status(running=True)
        self._task = asyncio.create_task(self._run(limit))
        return True

    async def stop(self) -> None:
        if self.running:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.status["running"] = False

    async def run_to_completion(self, limit: int | None = None) -> dict:
        """Synchronous variant for tests and scripts."""
        self.status = self._idle_status(running=True)
        await self._run(limit)
        return self.status

    async def _run(self, limit: int | None) -> None:
        try:
            sitemap = await self._fetch(SITEMAP_URL)
            urls = [u for u in _LOC_RE.findall(sitemap) if "/recipes/" in u]
            known = await self._store.catalog_known_urls()
            todo = sorted((u for u in urls if u not in known), key=_recency_key, reverse=True)
            if limit:
                todo = todo[:limit]
            self.status["total"] = len(todo)

            consecutive_errors = 0
            for url in todo:
                try:
                    entry = parse_recipe_page(await self._fetch(url), url)
                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    self.status["errors"] += 1
                    self.status["last_error"] = f"{url}: {e}"
                    logger.warning("Import failed for %s: %s", url, e)
                    if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                        logger.error("Import aborted after %d consecutive errors", consecutive_errors)
                        break
                    await asyncio.sleep(self._delay * 5)
                    continue
                if entry is None:
                    await self._store.catalog_mark_skipped(url, "incomplete")
                    self.status["skipped"] += 1
                else:
                    await self._store.catalog_add(entry)
                    self.status["imported"] += 1
                self.status["processed"] += 1
                await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Catalog import failed")
            self.status["last_error"] = str(e)
        finally:
            self.status["running"] = False
            if self._client is not None:
                await self._client.aclose()
                self._client = None
