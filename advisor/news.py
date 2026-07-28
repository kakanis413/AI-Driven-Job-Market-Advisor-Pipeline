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
    # A grounding URI backs exactly one headline. Without this, several articles
    # from the same publisher (Research.com routinely returns three) all matched the
    # first chunk for that domain and shipped identical URLs under different titles
    # — the same wrong-link failure as the old chunks[idx % len] fallback, just
    # reached a different way.
    used: set[str] = set()
    for raw in raw_items:
        title = str(raw.get("title") or "").strip()
        source = str(raw.get("source") or "Industry News").strip()
        want = _norm_domain(str(raw.get("source_domain") or ""))

        if not title:
            continue

        # Hard rule 1 (schemas.py): a URL must trace to an as-yet-unused grounding
        # chunk for the domain the model actually cited. Tracking `used` keeps
        # several articles from one publisher from all matching the first chunk
        # and shipping identical URLs. A wrong link is worse than a missing one,
        # so an unmatched item is dropped.
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
                # None when the model gave no date. Stamping today made every card
                # read as published-today and silently defeated the 90-day framing;
                # the schema already allows null and the card omits it.
                published=published[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", published) else None,
                summary=str(raw.get("summary") or "").strip()[:600],
                # Keyed on the CITED domain, not the URL. Every grounding URI is a
                # vertexaisearch redirect, so urlparse handed Google's own favicon
                # to every card regardless of the real publisher.
                favicon=f"https://www.google.com/s2/favicons?domain={want}&sz=64" if want else None,
            )
        )
        if len(items) >= MAX_ITEMS:
            break
    return items


# What a family's own articles tend to say. Used only to break cross-family ties,
# never to filter — a miss costs an article nothing except first claim on it.
# "Other" is a catch-all with no vocabulary of its own, so it never claims topically.
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
    """0 when the article talks about this family, 1 otherwise — so it sorts first.

    Rank alone sent a Forbes piece headlined "Why Humanities Majors Are 2026's
    Stealth Power Players" to Social sci, because it happened to lead there and
    place second under Humanities — leaving Humanities, the field it is actually
    about, a card short. Whether the field is named in the text is the better
    signal, and rank still decides when neither family is named or both are.
    """
    terms = _FAMILY_TERMS.get(family)
    if not terms:
        return 1
    haystack = f"{item.title} {item.summary}".lower()
    return 0 if any(t in haystack for t in terms) else 1


def _meta(page: str, prop: str) -> str | None:
    """Value of a <meta property|name="..." content="..."> tag, either attribute order."""
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
    """Follow the grounding redirect to the real article, lift its og: metadata.

    Every grounding URI is a vertexaisearch redirect, so following it is the only
    way to reach the publisher's own page — and the image is the whole point: the
    cards otherwise have nothing real to show. Failures are swallowed; an item
    without an image still renders, it just falls back to the publisher plate.

    Returns the item and the URL the redirect actually landed on. Two grounding
    URIs routinely point at one article, which comparing the URIs cannot catch;
    the resolved URL is what makes that duplicate detectable upstream.
    """
    try:
        r = await client.get(item.url)
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            return item, None
        page = r.text[:200_000]
        img = _meta(page, "og:image") or _meta(page, "twitter:image")
        if img and img.startswith("http"):
            item.image = img[:2000]
        # The publisher's own headline outranks the model's. Left alone, the model
        # paraphrases: one Forbes article arrived under three invented titles across
        # three families, so two of the three headlines on the page were never real.
        # Unescaped, because a meta tag carries entities the card would render
        # literally — "Gen Z Views AI &amp; College" on screen.
        title = _meta(page, "og:title") or _meta(page, "twitter:title")
        if title:
            item.title = html.unescape(title)[:300]
        # Fill a genuinely unknown date from the article itself rather than leaving
        # it blank — the real page is the only honest source for it.
        if item.published is None:
            pub = _meta(page, "article:published_time")
            if pub and re.match(r"^\d{4}-\d{2}-\d{2}", pub):
                item.published = pub[:10]
        return item, str(r.url)
    except (httpx.HTTPError, ValueError, UnicodeDecodeError):
        pass
    return item, None


async def _enrich_all(items: list[NewsItem]) -> tuple[list[NewsItem], dict[str, str]]:
    """Enrich concurrently, dropping only exact duplicates of the same article.

    Returns the items and a map of grounding URI -> the URL the redirect landed on.
    That map is the only way to tell that two different-looking grounding URIs are
    the same article, so the caller keeps it for cross-family deduplication.
    """
    if not items:
        return items, {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MajorVisualizerBot/1.0)"}
    async with httpx.AsyncClient(
        timeout=8.0, headers=headers, follow_redirects=True
    ) as client:
        pairs = await asyncio.gather(*(_enrich(client, it) for it in items))

    # Collapse items that resolved to the same article. Distinct grounding URIs can
    # redirect to one page, and the model gives each a differently-worded headline,
    # so the feed showed one story three times as three stories. Items whose URL
    # never resolved are kept — unknown is not the same as duplicate.
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
        # Grounding URI -> the URL its redirect resolves to. Two families are handed
        # different grounding URIs for one article, so this is what makes them
        # comparable; see _dedupe_across_families.
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
                # The file holds one non-family key for the resolved-URL map, and
                # older files may name families this build no longer knows.
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
            # Kept only for URIs still referenced by a cached feed, so the map does
            # not grow without bound across refreshes.
            live = {it.url for _, feed in self._cache.values() for it in feed.items}
            payload[RESOLVED_KEY] = {k: v for k, v in self._resolved.items() if k in live}
            CACHE_FILE.write_text(json.dumps(payload))
        except Exception as exc:
            log.warning("failed to persist news cache to disk: %s", exc)

    def _dedupe_across_families(self) -> None:
        """One article, one family.

        The search returns the same broadly-worded piece for many families — a
        single Forbes story on humanities majors was landing in five of eight,
        including STEM — so the feed showed one article as five different stories.

        The family that keeps it is the one whose own search ranked it highest, not
        whichever happened to fetch first. Rank is the only relevance signal on
        hand, and it is the right one: the story that leads Humanities' results and
        trails STEM's belongs to Humanities. Ties break on FAMILIES order so the
        outcome does not depend on which coroutine finished first.

        Runs over the whole cache after any store, which makes it idempotent and
        keeps prewarm and single-family refreshes on one code path.
        """
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

            # The grounded domains, which are the ONLY citations we may attach.
            # Vertex leaves web.domain unset and puts the domain in web.title, which
            # _norm_domain already handles upstream.
            domains = sorted({d for d, _ in chunks if d})

            # Re-extract whenever the first pass produced nothing we can cite —
            # either no JSON at all, or items whose source_domain matches no chunk.
            # Left unconstrained the model omits source_domain or invents one, and
            # every item then fails the hard-rule-1 check and the feed comes back
            # empty. Handing it the allowed list is what makes the rule satisfiable.
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
                # Real article images. Adds a few seconds to a fetch nobody waits on.
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
                # NOT request_timeout_s. That is 30s, tuned for a chat turn, while a
                # search-grounded news fetch measures 25-29s — so any fetch competing
                # with the prewarm burst tripped the timeout and surfaced a 503 on
                # the news tab. This path is background-refreshed and cached; it can
                # afford to wait.
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
        # Re-read: dedup may have removed items from the feed just stored, and the
        # caller returns this object straight to the client.
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
        # Inside the loop, not before it. A stale entry makes get_feed return the
        # cached feed immediately (it only kicks off a refresh), so without a sleep
        # per pass this becomes a hot spin — one that logs a line per iteration.
        await asyncio.sleep(REFRESH_CHECK_INTERVAL_S)
        for family in FAMILIES:
            try:
                hit = runtime._cache.get(family)
                if hit is None:
                    await runtime.get_feed(family)
                    continue
                remaining = hit[0] - time.time()
                # REFRESH_MARGIN_S buys a 6h feed a head start on expiry. An empty
                # feed's shorter TTL already *is* its retry interval, so applying the
                # margin to it would leave it permanently due — the condition that
                # made the missing sleep catastrophic rather than merely wasteful.
                due = remaining <= 0 or (hit[1].items and remaining < REFRESH_MARGIN_S)
                if due:
                    await runtime.get_feed(family)
            except Exception as exc:
                log.error("background refresh failed | family=%s: %s", family, exc)