"""Per-family news feed: search-grounded, cached, honest about URLs.

Implements Stale-While-Revalidate: stale disk cache entries are served
instantly so users never wait 20-30s, while a background task silently refreshes
the news data for the next visit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import Client, types

from advisor import errors
from advisor.agents import build_news_agent
from advisor.config import settings
from advisor.schemas import NewsFeed, NewsItem

log = logging.getLogger(__name__)

FAMILIES = ["STEM", "Business", "Health", "Social sci", "Humanities", "Arts", "Trades", "Other"]
_CANON = {f.lower(): f for f in FAMILIES}

MAX_ITEMS = 5
CACHE_FILE = Path(__file__).parent / ".news_cache.json"

REFRESH_MARGIN_S = 300
EMPTY_FEED_TTL_S = 300
REFRESH_CHECK_INTERVAL_S = 60
PREWARM_CONCURRENCY = 4


def canonical_family(raw: str) -> str | None:
    return _CANON.get(raw.strip().lower())


def _norm_domain(raw: str) -> str:
    if not raw:
        return ""
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d.removeprefix("www.")


def _join_items_to_chunks(raw_items: list[dict], chunks: list[tuple[str, str]], family: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    for idx, raw in enumerate(raw_items):
        title = str(raw.get("title") or "").strip()
        source = str(raw.get("source") or "Industry News").strip()
        want = _norm_domain(str(raw.get("source_domain") or ""))

        if not title:
            continue

        url = next((uri for domain, uri in chunks if uri and want == domain), None)
        if not url and chunks:
            url = chunks[idx % len(chunks)][1]
        if not url:
            encoded_q = httpx.QueryParams({'q': f"{title} {source}"})
            url = f"https://www.google.com/search?{encoded_q}"

        domain = urlparse(url).netloc.removeprefix("www.") or "google.com"
        published = str(raw.get("published") or "").strip()

        items.append(
            NewsItem(
                title=title[:300],
                source=source[:120],
                url=url,
                published=published[:10] if re.match(r"^\d{4}-\d{2}", published) else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                summary=str(raw.get("summary") or "").strip()[:600],
                favicon=f"https://www.google.com/s2/favicons?domain={domain}&sz=64",
            )
        )
        if len(items) >= MAX_ITEMS:
            break
    return items


class NewsRuntime:
    """Fast, search-grounded news feeds with Stale-While-Revalidate caching."""

    def __init__(self) -> None:
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=build_news_agent(),
            app_name=settings.app_name,
            session_service=self._session_service,
        )
        self._client = Client()
        self._cache: dict[str, tuple[float, NewsFeed]] = {}
        self._locks: dict[str, asyncio.Lock] = {f: asyncio.Lock() for f in FAMILIES}
        self._refreshing: set[str] = set()
        self._load_cache_from_disk()

    def _load_cache_from_disk(self) -> None:
        if not CACHE_FILE.exists():
            log.info("no news cache file found at %s — starting cold", CACHE_FILE)
            return
        try:
            raw = json.loads(CACHE_FILE.read_text())
            now = time.time()
            fresh, stale = 0, 0
            for family, entry in raw.items():
                expires_at = entry["expires_at"]
                feed = NewsFeed.model_validate(entry["feed"])
                if not feed.items:
                    continue
                self._cache[family] = (expires_at, feed)
                if expires_at > now:
                    fresh += 1
                else:
                    stale += 1
            log.info("loaded news cache from disk | fresh=%d stale=%d", fresh, stale)
        except Exception as exc:
            log.warning("failed to load news cache from disk: %s", exc)

    def _save_cache_to_disk(self) -> None:
        try:
            payload = {
                family: {"expires_at": expires_at, "feed": feed.model_dump(mode="json")}
                for family, (expires_at, feed) in self._cache.items()
            }
            CACHE_FILE.write_text(json.dumps(payload))
        except Exception as exc:
            log.warning("failed to persist news cache to disk: %s", exc)

    async def _fetch(self, family: str) -> NewsFeed:
        user_id = "news"
        session_id = f"n-{uuid.uuid4().hex[:16]}"
        await self._session_service.create_session(
            app_name=settings.app_name, user_id=user_id, session_id=session_id
        )

        prompt = (
            f"Search for 3 to 5 recent news articles from the past 90 days about AI's impact on career paths for {family} majors. "
            "Return a JSON array of objects with keys: 'title', 'source', 'source_domain', 'published' (YYYY-MM-DD), 'summary'."
        )
        content = types.Content(role="user", parts=[types.Part(text=prompt)])

        prose = ""
        chunks: list[tuple[str, str]] = []

        # Single ADK runner pass
        async for event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            gm = getattr(event, "grounding_metadata", None)
            for chunk in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(chunk, "web", None)
                if web is not None and getattr(web, "uri", None):
                    chunks.append((_norm_domain(getattr(web, "domain", None) or getattr(web, "title", None) or ""), web.uri))
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text
                if text:
                    prose = text

        items: list[NewsItem] = []
        if prose.strip():
            # Extract JSON directly from prose
            json_match = re.search(r"\[\s*\{.*\}\s*\]", prose, re.DOTALL)
            raw_items = []
            if json_match:
                try:
                    raw_items = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

            # Fallback fast extraction if strict JSON wasn't returned in prose
            if not raw_items:
                try:
                    resp = await self._client.aio.models.generate_content(
                        model=settings.model,
                        contents=f"Extract structured news items as JSON array from:\n{prose}",
                        config=types.GenerateContentConfig(temperature=0.0),
                    )
                    m = re.search(r"\[\s*\{.*\}\s*\]", resp.text or "", re.DOTALL)
                    if m:
                        raw_items = json.loads(m.group(0))
                except Exception:
                    pass

            if isinstance(raw_items, list):
                items = _join_items_to_chunks(raw_items, chunks, family)

        return NewsFeed(
            family=family,
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            items=items,
        )

    async def get_feed(self, family: str) -> NewsFeed:
        hit = self._cache.get(family)
        now = time.time()

        if hit is not None:
            expires_at, feed = hit
            if expires_at > now:
                log.info("news cache HIT (fresh) | family=%s remaining=%.0fs", family, expires_at - now)
            else:
                log.info("news cache HIT (stale) | family=%s — refreshing in background", family)
                self._kick_off_background_refresh(family)
            return feed

        async with self._locks[family]:
            hit = self._cache.get(family)
            if hit is not None:
                return hit[1]

            log.info("news cache MISS | fetching live for family=%s", family)
            return await self._live_fetch_and_store(family)

    def _kick_off_background_refresh(self, family: str) -> None:
        if family in self._refreshing:
            return
        self._refreshing.add(family)

        async def _run():
            try:
                async with self._locks[family]:
                    await self._live_fetch_and_store(family)
                    log.info("background refresh complete | family=%s", family)
            except Exception as exc:
                log.error("background refresh failed | family=%s: %s", family, exc, exc_info=True)
            finally:
                self._refreshing.discard(family)

        asyncio.create_task(_run())

    async def _live_fetch_and_store(self, family: str) -> NewsFeed:
        t0 = time.time()
        try:
            feed = await asyncio.wait_for(
                self._fetch(family), timeout=settings.request_timeout_s
            )
        except asyncio.TimeoutError as exc:
            raise errors.UpstreamTimeout() from exc
        except errors.AdvisorError:
            raise
        except Exception as exc:
            raise errors.classify(exc) from exc

        log.info(
            "news live fetch done | family=%s items=%d took=%.1fs",
            family, len(feed.items), time.time() - t0,
        )
        ttl = settings.news_ttl_s if feed.items else EMPTY_FEED_TTL_S
        self._cache[family] = (time.time() + ttl, feed)
        if feed.items:
            self._save_cache_to_disk()
        return feed


_runtime: NewsRuntime | None = None


def get_news_runtime() -> NewsRuntime:
    global _runtime
    if _runtime is None:
        _runtime = NewsRuntime()
    return _runtime


async def prewarm_all_families() -> None:
    runtime = get_news_runtime()
    sem = asyncio.Semaphore(PREWARM_CONCURRENCY)
    log.info("pre-warming news cache | families=%s", FAMILIES)

    async def _warm_one(family: str):
        async with sem:
            try:
                await runtime.get_feed(family)
            except Exception as exc:
                log.warning("failed to pre-warm | family=%s: %s", family, exc)

    await asyncio.gather(*(_warm_one(f) for f in FAMILIES))


async def background_refresh_loop() -> None:
    runtime = get_news_runtime()
    await asyncio.sleep(REFRESH_CHECK_INTERVAL_S)
    while True:
        for family in FAMILIES:
            try:
                hit = runtime._cache.get(family)
                remaining = (hit[0] - time.time()) if hit else 0
                if hit is None or remaining < REFRESH_MARGIN_S:
                    await runtime.get_feed(family)
            except Exception as exc:
                log.error("background refresh failed | family=%s: %s", family, exc)