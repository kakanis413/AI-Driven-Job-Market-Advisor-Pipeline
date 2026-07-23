"""Per-family news feed: search-grounded, cached, honest about URLs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
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
MAX_AGE_DAYS = 180

CACHE_FILE = Path(__file__).parent / ".news_cache.json"

REFRESH_MARGIN_S = 300
REFRESH_CHECK_INTERVAL_S = 60
PREWARM_CONCURRENCY = 2

_EXTRACT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "source": {"type": "string"},
            "source_domain": {"type": "string"},
            "published": {"type": "string", "nullable": True},
            "summary": {"type": "string"},
        },
        "required": ["title", "source", "source_domain", "summary"],
    },
}


def canonical_family(raw: str) -> str | None:
    return _CANON.get(raw.strip().lower())


def _norm_domain(raw: str) -> str:
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d.removeprefix("www.")


def _meta(html: str, prop: str) -> str | None:
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


def _clean_headline(title: str, source: str) -> str:
    t = re.sub(r'\s*[|–—-]\s*[^|–—-]{2,40}$', '', title).strip()
    return t or title


def _headline_from_slug(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.I)
    words = [w for w in re.split(r"[-_]+", slug) if w]
    if len(words) < 3 or all(w.isdigit() for w in words):
        return None
    return " ".join(w if w.isupper() else w.capitalize() for w in words)[:300]


def _is_source_title(title: str, source: str) -> bool:
    return _norm_domain(title) == _norm_domain(source) or title.strip().lower() in (
        source.strip().lower(),
        re.sub(r"\s*\([^)]*\)\s*$", "", source).strip().lower(),
    )


def _is_recent(published: str | None) -> bool:
    if not published:
        return True
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", published)
    if not m:
        return True
    try:
        d = datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - d <= timedelta(days=MAX_AGE_DAYS)


async def _enrich(client: httpx.AsyncClient, item: NewsItem) -> NewsItem:
    final_url = item.url
    try:
        r = await client.get(item.url, follow_redirects=True)
        final_url = str(r.url)
        final_host = urlparse(final_url).netloc.removeprefix("www.")
        item.favicon = f"https://www.google.com/s2/favicons?domain={final_host}&sz=64"
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            html = r.text[:200_000]
            og_title = _meta(html, "og:title") or _meta(html, "twitter:title")
            if og_title and _norm_domain(og_title) != _norm_domain(item.source):
                cleaned = _clean_headline(og_title, item.source)
                if len(cleaned) >= 12:
                    item.title = cleaned[:300]
            img = _meta(html, "og:image") or _meta(html, "twitter:image")
            if img and img.startswith("http"):
                item.image = img[:2000]
            pub = _meta(html, "article:published_time")
            if pub and re.match(r"^\d{4}-\d{2}-\d{2}", pub):
                item.published = pub[:10]
    except (httpx.HTTPError, ValueError):
        pass
    if _is_source_title(item.title, item.source):
        slug_title = _headline_from_slug(final_url)
        if slug_title:
            item.title = slug_title
    return item


async def _enrich_all(items: list[NewsItem]) -> list[NewsItem]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MajorVisualizerBot/1.0)"}
    async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
        enriched = await asyncio.gather(*(_enrich(client, it) for it in items))
    return [
        it
        for it in enriched
        if _is_recent(it.published) and not _is_source_title(it.title, it.source)
    ]


def _join_items_to_chunks(raw_items: list[dict], chunks: list[tuple[str, str]]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for raw in raw_items:
        title = str(raw.get("title") or "").strip()
        source = str(raw.get("source") or "").strip()
        want = _norm_domain(str(raw.get("source_domain") or ""))
        if not title or not source or not want:
            continue
        url = next((uri for domain, uri in chunks if uri and want == domain), None)
        if not url:
            continue
        published = str(raw.get("published") or "").strip()
        items.append(
            NewsItem(
                title=title[:300],
                source=source[:120],
                url=url,
                published=published[:20] if re.match(r"^\d{4}-\d{2}", published) else None,
                summary=str(raw.get("summary") or "").strip()[:600],
            )
        )
        if len(items) >= MAX_ITEMS:
            break
    return items


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
        self._locks: dict[str, asyncio.Lock] = {f: asyncio.Lock() for f in FAMILIES}
        self._load_cache_from_disk()

    def _load_cache_from_disk(self) -> None:
        if not CACHE_FILE.exists():
            log.info("no news cache file found at %s — starting cold", CACHE_FILE)
            return
        try:
            raw = json.loads(CACHE_FILE.read_text())
            now = time.time()
            loaded, skipped_expired = 0, 0
            for family, entry in raw.items():
                expires_at = entry["expires_at"]
                if expires_at <= now:
                    skipped_expired += 1
                    continue
                feed = NewsFeed.model_validate(entry["feed"])
                self._cache[family] = (expires_at, feed)
                loaded += 1
            log.info(
                "loaded news cache from disk | families=%d skipped_expired=%d",
                loaded, skipped_expired,
            )
        except Exception as exc:
            log.warning("failed to load news cache from disk, starting cold: %s", exc)

    def _save_cache_to_disk(self) -> None:
        try:
            payload = {
                family: {"expires_at": expires_at, "feed": feed.model_dump(mode="json")}
                for family, (expires_at, feed) in self._cache.items()
            }
            CACHE_FILE.write_text(json.dumps(payload))
        except Exception as exc:
            log.warning("failed to persist news cache to disk: %s", exc)

    async def _grounded_prose(self, family: str) -> tuple[str, list[tuple[str, str]]]:
        user_id = "news"
        session_id = f"n-{uuid.uuid4().hex[:16]}"
        await self._session_service.create_session(
            app_name=settings.app_name, user_id=user_id, session_id=session_id
        )
        prompt = (
            f"What is the latest news on AI's impact on careers for {family} majors? "
            "Find 3-5 recent items; for each, name the publication and when it was published."
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
                if web is not None and web.uri:
                    chunks.append((_norm_domain(web.domain or web.title or ""), web.uri))
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text
                if text:
                    prose = text
        return prose, chunks

    async def _extract_items(self, prose: str, domains: list[str]) -> list[dict]:
        resp = await self._client.aio.models.generate_content(
            model=settings.model,
            contents=(
                "Extract the news items from this digest as structured data.\n"
                f"ALLOWED source_domain values (use the one each item came from): {domains}\n"
                "Rules: only items actually present in the digest; source_domain MUST be "
                "one of the allowed values (skip the item if none fits); published as "
                "YYYY-MM-DD or null if the digest doesn't say; summary is 1-2 sentences "
                "in the digest's own framing.\n\n"
                f"DIGEST:\n{prose}"
            ),
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=_EXTRACT_SCHEMA,
            ),
        )
        try:
            parsed = json.loads(resp.text or "[]")
        except json.JSONDecodeError:
            return []
        return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []

    async def _fetch(self, family: str) -> NewsFeed:
        prose, chunks = await self._grounded_prose(family)
        items: list[NewsItem] = []
        if prose.strip() and chunks:
            domains = sorted({d for d, _ in chunks if d})
            raw = await self._extract_items(prose, domains)
            items = _join_items_to_chunks(raw, chunks)
            if len(raw) > len(items):
                log.info(
                    "news[%s]: dropped %d item(s) without a grounded URL",
                    family, len(raw) - len(items),
                )
            before = len(items)
            items = await _enrich_all(items)
            if before != len(items):
                log.info("news[%s]: dropped %d stale item(s)", family, before - len(items))
        return NewsFeed(
            family=family,
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            items=items,
        )

    async def get_feed(self, family: str) -> NewsFeed:
        hit = self._cache.get(family)
        now = time.time()
        if hit and hit[0] > now:
            log.info("news cache HIT | family=%s remaining=%.0fs", family, hit[0] - now)
            return hit[1]

        async with self._locks[family]:
            hit = self._cache.get(family)
            if hit and hit[0] > now:
                log.info("news cache HIT (after lock wait) | family=%s", family)
                return hit[1]

            log.info("news cache MISS | fetching live for family=%s", family)
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

            elapsed = time.time() - t0
            log.info("news live fetch done | family=%s took=%.1fs", family, elapsed)

            self._cache[family] = (time.time() + settings.news_ttl_s, feed)
            self._save_cache_to_disk()
            return feed


_runtime: NewsRuntime | None = None


def get_news_runtime() -> NewsRuntime:
    global _runtime
    if _runtime is None:
        _runtime = NewsRuntime()
    return _runtime


async def prewarm_all_families() -> None:
    """Warms every family concurrently (throttled), on startup."""
    runtime = get_news_runtime()
    sem = asyncio.Semaphore(PREWARM_CONCURRENCY)
    log.info("pre-warming news cache | families=%s concurrency=%d", FAMILIES, PREWARM_CONCURRENCY)

    async def _warm_one(family: str):
        async with sem:
            try:
                await runtime.get_feed(family)
            except Exception as exc:
                log.warning("failed to pre-warm | family=%s: %s", family, exc)

    await asyncio.gather(*(_warm_one(f) for f in FAMILIES))
    log.info("news prewarm complete")


async def background_refresh_loop() -> None:
    """Keeps every family's cache warm proactively."""
    runtime = get_news_runtime()
    log.info("news background refresh loop started")
    await asyncio.sleep(REFRESH_CHECK_INTERVAL_S)
    while True:
        for family in FAMILIES:
            try:
                hit = runtime._cache.get(family)
                remaining = (hit[0] - time.time()) if hit else 0
                if hit is None or remaining < REFRESH_MARGIN_S:
                    await runtime.get_feed(family)
            except Exception as exc:
                log.error("background refresh failed | family=%s: %s", family, exc, exc_info=True)
        await asyncio.sleep(REFRESH_CHECK_INTERVAL_S)