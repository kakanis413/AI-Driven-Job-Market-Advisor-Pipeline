"""Per-family news feed: search-grounded, cached, guaranteed image rendering.

Implements Stale-While-Revalidate: stale disk cache entries are served
instantly so users never wait, while a background task refreshes the news data.

IMAGES: resolved server-side, once per fetch, by pulling the real page's
og:image tag directly (no third-party embed API). The previous version used
api.microlink.io's live embed endpoint per <img> render, which meant every
browser view — not every cache refresh — spent a Microlink request. Free-tier
rate limits exhaust almost immediately under that pattern, which is why
images "worked, then silently died." Resolving og:image once per fetch and
storing it in the cached NewsItem removes that dependency entirely.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import httpx
from google.genai import Client, types

from advisor import errors
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
PREWARM_CONCURRENCY = 1

# Used ONLY when a real og:image can't be found on the actual page (blocked,
# no meta tag, fetch failed) — never as a first choice.
FAMILY_FALLBACK_IMAGES = {
    "STEM": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=600&q=80",
    "Business": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=600&q=80",
    "Health": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=600&q=80",
    "Social sci": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=600&q=80",
    "Humanities": "https://images.unsplash.com/photo-1457369804613-52c61a468e7d?auto=format&fit=crop&w=600&q=80",
    "Arts": "https://images.unsplash.com/photo-1513364776144-60967b0f800f?auto=format&fit=crop&w=600&q=80",
    "Trades": "https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=600&q=80",
    "Other": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=600&q=80",
}

_NEWS_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "source": {"type": "STRING"},
            "published": {"type": "STRING", "nullable": True},
            "summary": {"type": "STRING"},
            "url": {"type": "STRING", "nullable": True},
        },
        "required": ["title", "source", "summary"],
    },
}


def canonical_family(raw: str) -> str | None:
    return _CANON.get(raw.strip().lower())


def _meta(html: str, prop: str) -> str | None:
    """Read an og/meta tag's content, either attribute order, HTML-unescaped."""
    pat = re.escape(prop)
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']' + pat + r'["\'][^>]+content=["\']([^"\']+)',
        html, re.I,
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + pat + r'["\']',
        html, re.I,
    )
    if not m:
        return None
    import html as _h

    return _h.unescape(m.group(1)).strip() or None


async def _resolve_real_image(client: httpx.AsyncClient, item: NewsItem, family: str) -> None:
    """
    Fetches the actual article page once and pulls its real og:image (or
    twitter:image). Mutates item.image/item.favicon in place. Falls back to
    the family's placeholder ONLY if the real page yields nothing — never
    calls any third-party embed/proxy service.
    """
    try:
        r = await client.get(item.url, follow_redirects=True)
        final_host = urlparse(str(r.url)).netloc.removeprefix("www.")
        item.favicon = f"https://www.google.com/s2/favicons?domain={final_host}&sz=64"

        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            html = r.text[:200_000]
            img = _meta(html, "og:image") or _meta(html, "twitter:image")
            if img and img.startswith("http"):
                item.image = img[:2000]
                return
    except (httpx.HTTPError, ValueError):
        pass

    # Real page had no usable image, or the fetch itself failed — fall back
    # to a family placeholder rather than leaving the card image-less.
    item.image = FAMILY_FALLBACK_IMAGES.get(family, FAMILY_FALLBACK_IMAGES["Other"])


async def _resolve_all_images(items: list[NewsItem], family: str) -> None:
    if not items:
        return
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MajorVisualizerBot/1.0)"}
    async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:
        await asyncio.gather(*(_resolve_real_image(client, it, family) for it in items))


class NewsRuntime:
    """Fast, search-grounded news feeds with Stale-While-Revalidate caching."""

    def __init__(self) -> None:
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
        prompt = (
            f"Search for 3 to 5 recent news articles, hiring reports, or workforce analyses "
            f"from the past 90 days about AI's impact on job markets and career paths for {family} majors."
        )

        items: list[NewsItem] = []
        try:
            resp = await self._client.aio.models.generate_content(
                model=settings.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    tools=[{"google_search": {}}],
                    response_mime_type="application/json",
                    response_schema=_NEWS_SCHEMA,
                ),
            )

            chunk_urls = []
            candidates = getattr(resp, "candidates", None) or []
            if candidates and hasattr(candidates[0], "grounding_metadata"):
                gm = candidates[0].grounding_metadata
                for chunk in getattr(gm, "grounding_chunks", []) or []:
                    web = getattr(chunk, "web", None)
                    if web and getattr(web, "uri", None):
                        chunk_urls.append(getattr(web, "uri", ""))

            raw_text = resp.text or "[]"
            parsed = json.loads(raw_text)

            if isinstance(parsed, list):
                for idx, x in enumerate(parsed):
                    title = str(x.get("title") or "").strip()
                    source = str(x.get("source") or "Industry News").strip()
                    url = str(x.get("url") or "").strip()

                    if not url and chunk_urls:
                        url = chunk_urls[idx % len(chunk_urls)]

                    if not url or not url.startswith("http"):
                        url = f"https://www.google.com/search?q={quote_plus(title + ' ' + source)}"

                    domain = urlparse(url).netloc.removeprefix("www.") or "google.com"
                    published = str(x.get("published") or "").strip()

                    if title:
                        items.append(
                            NewsItem(
                                title=title[:300],
                                source=source[:120],
                                url=url,
                                image=None,  # resolved below, from the real page
                                published=published[:10] if re.match(r"^\d{4}-\d{2}", published) else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                                summary=str(x.get("summary") or "")[:600],
                                favicon=f"https://www.google.com/s2/favicons?domain={domain}&sz=64",
                            )
                        )

            items = items[:MAX_ITEMS]
            # One real fetch per article to pull its actual og:image — done
            # once here, at fetch/refresh time, not on every page render.
            await _resolve_all_images(items, family)

        except Exception as exc:
            log.error("fetch failed for family=%s: %s", family, exc)

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
    log.info("pre-warming news cache sequentially | families=%s", FAMILIES)

    async def _warm_one(family: str):
        async with sem:
            try:
                await runtime.get_feed(family)
                await asyncio.sleep(1.0)
            except Exception as exc:
                log.warning("failed to pre-warm | family=%s: %s", family, exc)

    for family in FAMILIES:
        await _warm_one(family)


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
        await asyncio.sleep(REFRESH_CHECK_INTERVAL_S)