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
from urllib.parse import urljoin

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
# Candidates to enrich before selecting. Wider than MAX_ITEMS because reachability,
# one-card-per-publisher and the date cut discard most of them.
CANDIDATE_CAP = 24

# SEO farms publishing one templated page per field. Excluded, not demoted — a
# demoted farm still ships when the feed is thin.
BLOCKED_DOMAINS = {"research.com"}

# Generic "AI and entry-level hiring" stories fit every family; uncapped, one article
# filled five tabs.
MAX_FAMILIES_PER_ARTICLE = 2

# The prompt's date window is a hint the model ignores, so enforce it here on the
# parsed date. Undated items rank last rather than being dropped.
MAX_AGE_DAYS = 45

# A hard 45d cut emptied Arts completely, so it widens for a family that would
# otherwise fall below SOFT_MIN_ITEMS. The denylist never widens.
SOFT_MIN_ITEMS = 3
RELAXED_MAX_AGE_DAYS = 120

# One search returns one slice of the index. The first two angles return much the
# same generic stories for every family; the third is what supplies family-specific
# candidates, and thin families need it to reach SOFT_MIN_ITEMS.
SEARCH_ANGLES = (
    "recent news articles about AI's impact on career paths and hiring for {family} majors",
    "recent reporting on how AI is changing entry-level jobs, required skills and the labor "
    "market for graduates in {family} fields",
    "recent news about specific {family} occupations, employers or programmes adapting to AI, "
    "naming the roles involved",
)

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


def _age_days(item: NewsItem) -> int | None:
    """Days since publication, or None when the item carries no usable date."""
    if not item.published:
        return None
    try:
        pub = datetime.strptime(item.published[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - pub).days


def _too_old(item: NewsItem, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """True only for items we can date AND that exceed the window. Undated items are
    never dropped here — they are demoted in _select_cards instead, so a thin family
    keeps a plausible card rather than showing an empty tab."""
    age = _age_days(item)
    return age is not None and age > max_age_days


def _join_items_to_chunks(
    raw_items: list[dict], chunks: list[tuple[str, str]], family: str
) -> list[tuple[str, NewsItem]]:
    """Match each extracted item to an unused grounding chunk — candidates only.

    Quality ranking and the MAX/MIN cut happen later in _select_cards, once
    enrichment has revealed which sources we could actually reach. Returns
    (registrable_domain, item) pairs so selection can group cards by publisher.
    """
    candidates: list[tuple[str, NewsItem]] = []
    used: set[str] = set()
    for raw in raw_items:
        title = str(raw.get("title") or "").strip()
        # The model narrates its sourcing here — "PwC (via Remote Autopilot)" — and the
        # uppercased card truncates mid-parenthetical. Keep the publisher only.
        source = re.sub(r"\s*\((?:[^()]|\([^()]*\))*\)\s*$", "", str(raw.get("source") or "").strip())
        source = re.sub(r"\s+", " ", source).strip(" -–—|") or "Industry News"
        want = _norm_domain(str(raw.get("source_domain") or ""))

        if not title:
            continue

        # Hard rule 1: a URL must trace to an as-yet-unused grounding chunk for the
        # cited domain. `used` stops several articles from one publisher all matching
        # its first chunk and shipping identical URLs. A wrong link is worse than a
        # missing one, so an unmatched item is dropped.
        url = next(
            (uri for domain, uri in chunks if uri and want == domain and uri not in used),
            None,
        )
        if not url:
            log.info("news[%s]: dropped %r — no free grounding chunk for %r", family, title[:48], want)
            continue
        used.add(url)

        published = str(raw.get("published") or "").strip()

        candidates.append((
            want,
            NewsItem(
                title=title[:300],
                source=source[:120],
                url=url,
                # None when the model gave no date. Stamping today made every card
                # read as published-today and defeated the 90-day framing; the schema
                # allows null and the card omits it.
                published=published[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", published) else None,
                summary=str(raw.get("summary") or "").strip()[:600],
                # Keyed on the CITED domain, not the URL. Every grounding URI is a
                # vertexaisearch redirect, so urlparse handed Google's favicon to
                # every card regardless of the real publisher.
                favicon=f"https://www.google.com/s2/favicons?domain={want}&sz=64" if want else None,
            ),
        ))
        if len(candidates) >= CANDIDATE_CAP:
            break
    return candidates


def _select_cards(
    items: list[NewsItem],
    verified_urls: set[str],
    domain_by_url: dict[str, str],
    family: str,
) -> list[NewsItem]:
    """Pick the final cards: illustrated and reachable first, one per publisher.

    Quality is judged on imagery and reachability rather than a name list, so it
    still works when the next content farm shows up. Denylisted and over-age items
    are removed before ranking so a shortage of alternatives can never promote them;
    if that leaves fewer than SOFT_MIN_ITEMS, the age cut alone widens and selection
    reruns.
    """
    def tier(item: NewsItem) -> int:
        reachable = item.url in verified_urls
        return 0 if reachable else 1

    def pick(max_age_days: int) -> list[NewsItem]:
        # Excluded before ranking, not demoted within it: a denylisted farm must
        # never ship, even when it is the only candidate left.
        eligible = [
            it for it in items
            if domain_by_url.get(it.url, "") not in BLOCKED_DOMAINS
            and not _too_old(it, max_age_days)
        ]

        # Keys in order: has an image, reachable, on-topic, dated, newest.
        # Imagery leads because it doubles as the quality signal — job boards and PR
        # wires carry no article and so no og:image, real publishers nearly always do,
        # which sorts them apart without a domain list to maintain.
        ranked = sorted(
            enumerate(eligible),
            key=lambda pair: (
                not pair[1].image,
                tier(pair[1]),
                _topical_miss(family, pair[1]),
                _age_days(pair[1]) is None,
                _age_days(pair[1]) if _age_days(pair[1]) is not None else 0,
                pair[0],
            ),
        )

        chosen: list[NewsItem] = []
        shown_domains: set[str] = set()
        shown_sources: set[str] = set()
        for _idx, item in ranked:
            if len(chosen) >= MAX_ITEMS:
                break
            domain = domain_by_url.get(item.url, "")
            # One card per publisher, on domain AND source name. Domain alone missed
            # "Associated Builders and Contractors" shipping twice from two chapter
            # sites (abccentraltexas.org, abccarolinas.org).
            source_key = re.sub(r"[^a-z0-9]", "", (item.source or "").lower())[:24]
            if domain and domain in shown_domains:
                continue
            if source_key and source_key in shown_sources:
                log.info("news[%s]: dropped %r — same publisher as an earlier card",
                         family, item.title[:48])
                continue
            chosen.append(item)
            if domain:
                shown_domains.add(domain)
            if source_key:
                shown_sources.add(source_key)
        return chosen

    for it in items:
        if domain_by_url.get(it.url, "") in BLOCKED_DOMAINS:
            log.info("news[%s]: dropped %r — denylisted domain", family, it.title[:48])

    chosen = pick(MAX_AGE_DAYS)
    if len(chosen) < SOFT_MIN_ITEMS:
        widened = pick(RELAXED_MAX_AGE_DAYS)
        if len(widened) > len(chosen):
            log.info(
                "news[%s]: only %d card(s) within %dd — widening to %dd, now %d",
                family, len(chosen), MAX_AGE_DAYS, RELAXED_MAX_AGE_DAYS, len(widened),
            )
            chosen = widened

    # An initials plate reads as a card that failed to load, so drop imageless cards
    # once there are enough illustrated ones to fill a row.
    illustrated = [it for it in chosen if it.image]
    if len(illustrated) >= SOFT_MIN_ITEMS and len(illustrated) < len(chosen):
        log.info(
            "news[%s]: dropped %d imageless card(s) — %d illustrated already",
            family, len(chosen) - len(illustrated), len(illustrated),
        )
        chosen = illustrated
    return chosen


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


def _lead_image(page: str, base_url: str) -> str | None:
    """Best lead image for a card, or None (the card then draws an initials plate).

    Publishers each pick one of these shapes and stick to it, so every tag checked
    here is one less monogram in the grid.
    """
    candidates = [
        _meta(page, "og:image"),
        _meta(page, "og:image:secure_url"),
        _meta(page, "og:image:url"),
        _meta(page, "twitter:image"),
        _meta(page, "twitter:image:src"),
        _meta(page, "image"),
    ]

    m = re.search(r'<link[^>]+rel=["\']image_src["\'][^>]*href=["\']([^"\']+)["\']', page, re.I)
    if m:
        candidates.append(m.group(1))

    # JSON-LD: "image" is either a bare URL, an array, or an ImageObject with "url".
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I
    )[:4]:
        m = re.search(r'"image"\s*:\s*(?:\[\s*)?(?:\{[^{}]*?"url"\s*:\s*)?"([^"]+)"', block)
        if m:
            candidates.append(m.group(1))

    for raw in candidates:
        if not raw:
            continue
        url = html.unescape(raw.strip())
        # Resolve protocol-relative (//cdn/x.jpg) and root-relative (/media/x.jpg)
        # against the page. Requiring an http prefix threw both away, which is why
        # reachable publishers were still landing on the initials plate.
        if url.startswith("//") or url.startswith("/") or not url.startswith("http"):
            url = urljoin(base_url, url)
        if url.startswith("http") and not url.lower().endswith(".svg"):
            return url[:2000]
    return None


async def _enrich(client: httpx.AsyncClient, item: NewsItem) -> tuple[NewsItem, str | None]:
    try:
        r = await client.get(item.url)
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            return item, None
        page = r.text[:200_000]
        img = _lead_image(page, str(r.url))
        if img:
            item.image = img

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
    # Identifiable UA, but with the Accept headers a browser sends — without them
    # some CDNs refuse us, and a failed fetch costs both the publisher URL and image.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; BeyondTheDegreeBot/1.0; +link-preview) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # 5s not 8s: these run concurrently, so the slowest page bounds the cold fetch.
    async with httpx.AsyncClient(
        timeout=5.0, headers=headers, follow_redirects=True
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

        # Families showing each article. Every key starts at 1 — its owning family —
        # so a yield below takes it to 2 and the next one is refused.
        reuse: dict[str, int] = {key: 1 for key in owner}

        changed = False
        for family, (expires_at, feed) in list(self._cache.items()):
            fam_rank = FAMILIES.index(family) if family in FAMILIES else len(FAMILIES)
            kept = []
            surrendered: list[NewsItem] = []
            for rank, item in enumerate(feed.items):
                key = self._resolved.get(item.url, item.url)
                if owner[key] == (_topical_miss(family, item), rank, fam_rank):
                    kept.append(item)
                else:
                    surrendered.append(item)

            # Ownership yields while a family sits below SOFT_MIN_ITEMS, so dedupe can
            # never empty a tab — but only up to MAX_FAMILIES_PER_ARTICLE.
            while len(kept) < SOFT_MIN_ITEMS and surrendered:
                item = surrendered.pop(0)
                key = self._resolved.get(item.url, item.url)
                if reuse[key] >= MAX_FAMILIES_PER_ARTICLE:
                    log.info("news[%s]: dropped %r — already shown in %d families",
                             family, item.title[:48], reuse[key])
                    changed = True
                    continue
                reuse[key] += 1
                kept.append(item)
            for item in surrendered:
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

    async def _search_once(self, family: str, angle: str) -> tuple[str, list[tuple[str, str]]]:
        """One grounded search. Returns (model prose, grounding chunks)."""
        user_id = "news"
        session_id = f"n-{uuid.uuid4().hex[:16]}"
        await self._session_service.create_session(
            app_name=settings.app_name, user_id=user_id, session_id=session_id
        )

        prompt = (
            # Ask wide: grounding-chunk matching, reachability ranking and
            # one-card-per-publisher discard most candidates, so a request for a few
            # returns fewer. Over-asking is what lets selection prefer real
            # publishers over content-farm filler and still fill the field.
            f"Search for 8 to 12 {angle.format(family=family)}, "
            f"published within the last {MAX_AGE_DAYS} days. "
            # The date window is enforced again in _select_cards; this only biases
            # the search. The source steer is worth stating because the default
            # results skew to university admissions pages and SEO listicles.
            "Strongly prefer news organisations, research institutes and government "
            "labour statistics over university marketing pages, admissions blogs and "
            "SEO listicles. "
            "Return a JSON array of objects with keys: 'title', 'source', 'source_domain', "
            "'published' (YYYY-MM-DD), 'summary'."
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

        return prose, chunks

    async def _extract_raw_items(
        self, prose: str, chunks: list[tuple[str, str]], family: str
    ) -> list[dict]:
        """Parse the model's JSON array, re-asking once if it cited no real domain."""
        json_match = re.search(r"\[\s*\{.*\}\s*\]", prose, re.DOTALL)
        raw_items: list = []
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

        return [i for i in raw_items if isinstance(i, dict)] if isinstance(raw_items, list) else []

    async def _fetch(self, family: str) -> NewsFeed:
        # Search every angle concurrently and pool the results. One search returns
        # one slice of the index; pooling two is what lifted feeds off 2–3 cards.
        # return_exceptions so a single failed angle degrades the feed rather than
        # emptying it.
        results = await asyncio.gather(
            *(self._search_once(family, angle) for angle in SEARCH_ANGLES),
            return_exceptions=True,
        )

        chunks: list[tuple[str, str]] = []
        raw_items: list[dict] = []
        for result in results:
            if isinstance(result, BaseException):
                log.warning("news[%s]: search angle failed: %s", family, result)
                continue
            prose, angle_chunks = result
            chunks.extend(angle_chunks)
            if prose.strip():
                raw_items.extend(await self._extract_raw_items(prose, angle_chunks, family))

        items: list[NewsItem] = []
        if raw_items:
            candidates = _join_items_to_chunks(raw_items, chunks, family)
            domain_by_url = {it.url: dom for dom, it in candidates}
            # Enrich every candidate (this is what reveals reachability), then
            # let source quality decide which become cards.
            enriched, resolved = await _enrich_all([it for _, it in candidates])
            self._resolved.update(resolved)
            items = _select_cards(enriched, set(resolved), domain_by_url, family)

            # Serve the publisher's URL, not the grounding redirect — those are
            # temporary, so shared cards eventually 404. After selection, because
            # domain_by_url and the reachability set are keyed on the redirect.
            for item in items:
                item.url = self._resolved.get(item.url, item.url)

        log.info(
            "news[%s]: %d candidates from %d angles → %d cards",
            family, len(raw_items), len(SEARCH_ANGLES), len(items),
        )
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
            # Reassign any article now shared with another family to its single best
            # home (topical match, then rank) and drop it from the rest. Runs over the
            # whole cache, so it converges as families fill in during prewarm. Returns
            # this family's possibly-trimmed feed below.
            self._dedupe_across_families()
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