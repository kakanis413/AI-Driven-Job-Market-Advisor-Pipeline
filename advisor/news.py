"""Per-family news feed: search-grounded, cached, honest about URLs.

NEWS_TAB.md §6: family buckets, precomputed lazily with a TTL — the first
request for a family pays the search, everyone after gets the cache.

Hard rule 1 lives here: item URLs are taken ONLY from Google Search grounding
chunks. Two phases, because Vertex only attaches grounding chunks to natural
prose (structured JSON output suppresses citation mapping — verified against
gemini-3.5-flash):

  1. the same prose `news_agent` the chat uses runs with google_search and
     yields cited prose + grounding chunks (domain + redirect URI);
  2. a toolless structured-output call extracts card items from that prose,
     with `source_domain` constrained to the grounded domains.

Items are then joined to chunks by domain; an item that matches no chunk is
dropped, not rendered. The model never composes a URL.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
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

# Mirrors FAMILY_ORDER in src/design/tokens.ts — the buckets are the contract.
FAMILIES = ["STEM", "Business", "Health", "Social sci", "Humanities", "Arts", "Trades", "Other"]
_CANON = {f.lower(): f for f in FAMILIES}

MAX_ITEMS = 5
# Recent signal only: an article older than this is dropped, so the tab never
# labels a months-old piece "just now".
MAX_AGE_DAYS = 180

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
    """Read an og/meta tag content (either attribute order), decoded."""
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
    """Strip a trailing " | Publisher" / " - Publisher" site-name suffix."""
    t = re.sub(r'\s*[|–—-]\s*[^|–—-]{2,40}$', '', title).strip()
    return t or title


def _headline_from_slug(url: str) -> str | None:
    """Fallback headline from a REAL resolved-URL slug when og:title is blocked
    (e.g. Cloudflare). Derived from fetched page data, not invented."""
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.I)
    words = [w for w in re.split(r"[-_]+", slug) if w]
    if len(words) < 3 or all(w.isdigit() for w in words):
        return None
    return " ".join(w if w.isupper() else w.capitalize() for w in words)[:300]


def _is_source_title(title: str, source: str) -> bool:
    """The model sometimes uses the publication as the 'headline'. Detect it so
    such items get a real headline or get dropped — never shown source-as-title."""
    return _norm_domain(title) == _norm_domain(source) or title.strip().lower() in (
        source.strip().lower(),
        re.sub(r"\s*\([^)]*\)\s*$", "", source).strip().lower(),  # strip "(BPC)"
    )


def _is_recent(published: str | None) -> bool:
    """Keep items with no date (can't judge) or dated within MAX_AGE_DAYS."""
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
    """Fetch the REAL article page behind the grounded URL and pull the true
    headline (og:title), thumbnail (og:image) and published date. Favicon is
    derived from the resolved publisher domain. Everything is from the fetched
    page or dropped — nothing invented. Failure degrades to no image."""
    final_url = item.url
    try:
        r = await client.get(item.url, follow_redirects=True)
        final_url = str(r.url)
        final_host = urlparse(final_url).netloc.removeprefix("www.")
        item.favicon = f"https://www.google.com/s2/favicons?domain={final_host}&sz=64"
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            html = r.text[:200_000]
            og_title = _meta(html, "og:title") or _meta(html, "twitter:title")
            # The page's own og:title is the real headline; prefer it.
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
    # If we still don't have a real headline (page blocked / model used the
    # source name), derive one from the real resolved-URL slug.
    if _is_source_title(item.title, item.source):
        slug_title = _headline_from_slug(final_url)
        if slug_title:
            item.title = slug_title
    return item


async def _enrich_all(items: list[NewsItem]) -> list[NewsItem]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MajorVisualizerBot/1.0)"}
    async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
        enriched = await asyncio.gather(*(_enrich(client, it) for it in items))
    # Drop stale items, and any still showing the source as the headline (no
    # real article headline could be obtained) — better nothing than a fake card.
    return [
        it
        for it in enriched
        if _is_recent(it.published) and not _is_source_title(it.title, it.source)
    ]


def _join_items_to_chunks(raw_items: list[dict], chunks: list[tuple[str, str]]) -> list[NewsItem]:
    """chunks: (domain, uri). An item keeps only a grounded URL or dies."""
    items: list[NewsItem] = []
    for raw in raw_items:
        title = str(raw.get("title") or "").strip()
        source = str(raw.get("source") or "").strip()
        want = _norm_domain(str(raw.get("source_domain") or ""))
        if not title or not source or not want:
            continue
        url = next((uri for domain, uri in chunks if uri and want == domain), None)
        if not url:
            continue  # hard rule 1: no grounded URL, no card
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
    """One runner + a per-family TTL cache. Built lazily at first request."""

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

    async def _grounded_prose(self, family: str) -> tuple[str, list[tuple[str, str]]]:
        """Phase 1: cited prose + (domain, uri) grounding chunks."""
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
                    # On Vertex the domain arrives in `title`; `domain` is often unset.
                    chunks.append((_norm_domain(web.domain or web.title or ""), web.uri))
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text
                if text:
                    prose = text
        return prose, chunks

    async def _extract_items(self, prose: str, domains: list[str]) -> list[dict]:
        """Phase 2: structured extraction, no tools, domains constrained."""
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
        import json

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
            # Enrich from the real pages (headline, thumbnail, favicon, date) and
            # drop anything that turns out to be stale.
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
        if hit and hit[0] > time.monotonic():
            return hit[1]
        async with self._locks[family]:
            hit = self._cache.get(family)  # a queued waiter finds it fresh
            if hit and hit[0] > time.monotonic():
                return hit[1]
            try:
                feed = await asyncio.wait_for(
                    self._fetch(family), timeout=settings.request_timeout_s
                )
            except asyncio.TimeoutError as exc:
                raise errors.UpstreamTimeout() from exc
            except errors.AdvisorError:
                raise
            except Exception as exc:  # noqa: BLE001 - surfaced as structured error
                raise errors.classify(exc) from exc
            self._cache[family] = (time.monotonic() + settings.news_ttl_s, feed)
            return feed


_runtime: NewsRuntime | None = None


def get_news_runtime() -> NewsRuntime:
    global _runtime
    if _runtime is None:
        _runtime = NewsRuntime()
    return _runtime
