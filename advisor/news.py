"""Per-family news feed: search-grounded, cached, honest about URLs.

Implements Stale-While-Revalidate: stale disk cache entries are served
instantly so users never wait 20-30s, while a background task silently refreshes
the news data for the next visit.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

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
# Top-level key in the cache file holding the resolved-URL map. Not a family name,
# and deliberately prefixed so it can never collide with one.
RESOLVED_KEY = "_resolved_urls"

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
    used: set[str] = set()
    for raw in raw_items:
        title = str(raw.get("title") or "").strip()
        source = str(raw.get("source") or "Industry News").strip()
        want = _norm_domain(str(raw.get("source_domain") or ""))

        if not title:
            continue

        url = next(
            (uri for domain, uri in chunks if uri and want == domain and uri not in used),
            None,
        )
        if not url:
            log.info("news[%s]: dropped %r — no free grounding chunk for %r", family, title[:48], want)
            continue
        used.add(url)

        published = str(raw.get("published") or "").strip()

        items.append(
            NewsItem(
                title=title[:300],
                source=source[:120],
                url=url,
                published=published[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", published) else None,
                summary=str(raw.get("summary") or "").strip()[:600],
                favicon=f"https://www.google.com/s2/favicons?domain={want}&sz=64" if want else None,
            )
        )
        if len(items) >= MAX_ITEMS:
            break
    return items


_FAMILY_TERMS = {
    "STEM": ("stem", "engineering", "computer science"),
    "Business": ("business", "mba", "finance", "marketing"),
    "Health": ("health", "nursing", "medical", "clinical"),
    "Social sci": ("social science", "sociology", "psychology", "economics"),
    "Humanities": ("humanities", "liberal arts", "english", "history", "philosophy"),
    "Arts": ("art", "design", "creative", "music"),
    "Trades": ("trades", "vocational", "apprentice", "blue collar", "blue-collar"),
}


def _topical_miss(family: str, item: NewsItem) -> int:
    terms = _FAMILY_TERMS.get(family)
    if not terms:
        return 1
    haystack = f"{item.title} {item.summary}".lower()
    return 0 if any(t in haystack for t in terms) else 1


def _meta(page: str, prop: str) -> str | None:
    esc = re.escape(prop)
    for pattern in (
        rf'<meta[^>]+(?:property|name)=["\']{esc}["\'][^>]*content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{esc}["\']',
    ):
        m = re.search(pattern, page, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


async def _enrich(client: httpx.AsyncClient, item: NewsItem) -> tuple[NewsItem, str | None]:
    try:
        r = await client.get(item.url)
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            return item, None
        page = r.text[:200_000]
        img = _meta(page, "og:image") or _meta(page, "twitter:image")
        
        if img and img.startswith("http"):
            # Update applied here: Ensuring both potential frontend schema keys are populated 
            # so Pydantic successfully serializes the image link regardless of the model definition.
            try:
                item.image_url = img[:2000]
            except Exception:
                pass
            try:
                item.image = img[:2000]
            except Exception:
                pass

        title = _meta(page, "og:title") or _meta(page, "twitter:title")
        if title:
            item.title = html.unescape(title)[:300]
            
        if item.published is None:
            pub = _meta(page, "article:published_time")
            if pub and re.match(r"^\d{4}-\d{2}-\d{2}", pub):
                item.published = pub[:10]
        return item, str(r.url)
    except (httpx.HTTPError, ValueError, UnicodeDecodeError):
        pass
    return item, None


async def _enrich_all(items: list[NewsItem]) -> tuple[list[NewsItem], dict[str, str]]:
    if not items:
        return items, {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MajorVisualizerBot/1.0)"}
    async with httpx.AsyncClient(
        timeout=8.0, headers=headers, follow_redirects=True
    ) as client:
        pairs = await asyncio.gather(*(_enrich(client, it) for it in items))

    deduped: list[NewsItem] = []
    seen: set[str] = set()
    resolved_by_url: dict[str, str] = {}
    for item, resolved in pairs:
        if resolved is not None:
            if resolved in seen:
                log.info("news: dropped duplicate of %s", resolved[:80])
                continue
            seen.add(resolved)
            resolved_by_url[item.url] = resolved
        deduped.append(item)
    return deduped, resolved_by_url


class NewsRuntime:
    def __init__(self) -> None:
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=build_news_agent(),
            app_name=settings.app_name,
            session_service=self._session_service,
        )
        self._client = Client()
        self._cache: dict[str, tuple[float, NewsFeed]] = {}
        self._resolved: dict[str, str] = {}
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
            self._resolved = dict(raw.get(RESOLVED_KEY) or {})
            for family, entry in raw.items():
                if family not in FAMILIES:
                    continue
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
            payload: dict[str, object] = {
                family: {"expires_at": expires_at, "feed": feed.model_dump(mode="json")}
                for family, (expires_at, feed) in self._cache.items()
            }
            live = {it.url for _, feed in self._cache.values() for it in feed.items}
            payload[RESOLVED_KEY] = {k: v for k, v in self._resolved.items() if k in live}
            CACHE_FILE.write_text(json.dumps(payload))
        except Exception as exc:
            log.warning("failed to persist news cache to disk: %s", exc)

    def _dedupe_across_families(self) -> None:
        owner: dict[str, tuple[int, int, int]] = {}
        for family, (_, feed) in self._cache.items():
            fam_rank = FAMILIES.index(family) if family in FAMILIES else len(FAMILIES)
            for rank, item in enumerate(feed.items):
                key = self._resolved.get(item.url, item.url)
                bid = (_topical_miss(family, item), rank, fam_rank)
                if key not in owner or bid < owner[key]:
                    owner[key] = bid

        changed = False
        for family, (expires_at, feed) in list(self._cache.items()):
            fam_rank = FAMILIES.index(family) if family in FAMILIES else len(FAMILIES)
            kept = []
            for rank, item in enumerate(feed.items):
                key = self._resolved.get(item.url, item.url)
                if owner[key] == (_topical_miss(family, item), rank, fam_rank):
                    kept.append(item)
                else:
                    changed = True
                    log.info(
                        "news[%s]: dropped %r — same article already owned by another family",
                        family, item.title[:48],
                    )
            if len(kept) != len(feed.items):
                self._cache[family] = (
                    expires_at,
                    feed.model_copy(update={"items": kept}),
                )
        if changed:
            self._save_cache_to_disk()

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
            json_match = re.search(r"\[\s*\{.*\}\s*\]", prose, re.DOTALL)
            raw_items = []
            if json_match:
                try:
                    raw_items = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

            domains = sorted({d for d, _ in chunks if d})

            usable = any(
                isinstance(i, dict) and _norm_domain(str(i.get("source_domain") or "")) in domains
                for i in (raw_items if isinstance(raw_items, list) else [])
            )
            if domains and not usable:
                try:
                    resp = await self._client.aio.models.generate_content(
                        model=settings.model,
                        contents=(
                            "Extract the news items below as a JSON array with keys "
                            "'title', 'source', 'source_domain', 'published', 'summary'.\n"
                            f"'source_domain' MUST be exactly one of: {', '.join(domains)}\n"
                            "Set 'published' to YYYY-MM-DD only if the text states a date; "
                            "otherwise use null. Never guess a date.\n\n"
                            f"{prose}"
                        ),
                        config=types.GenerateContentConfig(temperature=0.0),
                    )
                    m = re.search(r"\[\s*\{.*\}\s*\]", resp.text or "", re.DOTALL)
                    if m:
                        raw_items = json.loads(m.group(0))
                except Exception as exc:
                    log.warning("news[%s]: structured re-extraction failed: %s", family, exc)

            if isinstance(raw_items, list):
                items = _join_items_to_chunks(raw_items, chunks, family)
                items, resolved = await _enrich_all(items)
                self._resolved.update(resolved)

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
                self._fetch(family), timeout=settings.news_fetch_timeout_s
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
        return self._cache[family][1]


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
    while True:
        await asyncio.sleep(REFRESH_CHECK_INTERVAL_S)
        for family in FAMILIES:
            try:
                hit = runtime._cache.get(family)
                if hit is None:
                    await runtime.get_feed(family)
                    continue
                remaining = hit[0] - time.time()
                due = remaining <= 0 or (hit[1].items and remaining < REFRESH_MARGIN_S)
                if due:
                    await runtime.get_feed(family)
            except Exception as exc:
                log.error("background refresh failed | family=%s: %s", family, exc)